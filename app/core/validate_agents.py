import os
import json
import logging
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic_core import ValidationError
from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from dotenv import load_dotenv
from app.logging_config import logger

load_dotenv()

def get_chat_openai_params(model: str, reasoning_effort: str, max_tokens: int, base_url: str, api_key: str) -> Dict:
    """Helper to compute ChatOpenAI params based on model and reasoning_effort."""
    gpt5_variants = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
    temperature = None if model in gpt5_variants else float(os.getenv("TEMPERATURE", "0.5"))
    model_kwargs = {"reasoning": {"effort": reasoning_effort}} if model in gpt5_variants else {}
    # Enforce JSON mode to ensure responses are valid JSON strings
    model_kwargs["response_format"] = {"type": "json_object"}
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "max_tokens": max_tokens,
        "model_kwargs": model_kwargs,
        "temperature": temperature
    }

# Pydantic Models (unchanged)
class ConfidenceResult(BaseModel):
    """Structured output for confidence calculation"""
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Brief explanation of why this score was assigned")

class FeedbackCheckValidationAgent(BaseModel):
    """Pydantic model to store validation results"""
    feedback: str
    primary_issue: str

class RefinementResult(BaseModel):
    """Pydantic model for refinement output"""
    verbatim_answer: str
    explanation: Optional[str]

class ValidationResult(BaseModel):
    """Pydantic model to store validation results"""
    feedback: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

class IterationResult(BaseModel):
    """Pydantic model to store results of each iteration"""
    iteration: int
    original_answer: str
    original_explanation: Optional[str]
    validation_result: ValidationResult
    improved_answer: str
    improved_explanation: Optional[str]
    timestamp: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

class ConfidenceAgent:
    """Agent responsible for calculating confidence scores"""
    
    def __init__(
            self,
            api_key: Optional[str] = None,
            llm_model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-4.1-mini"),
            reasoning_effort: str = os.getenv("REASONING_EFFORT", "low"),
            max_completion_tokens: int = int(os.getenv("MAX_RESPONSE_TOKENS", 1000)),
    ):
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.api_key:
            raise ValueError("LiteLLM Master Key is required")
        
        self.model = llm_model
        self.reasoning_effort = reasoning_effort
        self.max_completion_tokens = max_completion_tokens
        self.parser = PydanticOutputParser(pydantic_object=ConfidenceResult)
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:4000")
        
        logger.debug(f"Initializing ConfidenceAgent with model={llm_model}, base_url={base_url}, "
                     f"reasoning_effort={reasoning_effort}, max_tokens={max_completion_tokens}")
        
        params = get_chat_openai_params(self.model, self.reasoning_effort, self.max_completion_tokens, base_url, self.api_key)
        self.client = ChatOpenAI(**params, streaming=False)
        
        self.confidence_prompt = self._create_confidence_prompt()
        self.no_chunks_confidence_prompt = self._create_no_chunks_confidence_prompt()

    def _extract_text_from_content(self, content: any) -> str:
        """Extract plain text from potentially structured LLM response content."""
        try:
            if content is None:
                return ""
                
            if isinstance(content, str):
                # Try to parse as JSON first if it looks like JSON
                content = content.strip()
                if (content.startswith('{') and content.endswith('}')) or \
                   (content.startswith('[') and content.endswith(']')):
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            # Extract 'feedback' or 'answer' fields if present
                            return parsed.get('feedback', parsed.get('answer', str(parsed)))
                        return str(parsed)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, return as-is
                        pass
                logger.debug(f"Response content is string: {content[:200]}...")
                return content
                
            elif isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif 'feedback' in part:
                            text_parts.append(part['feedback'])
                        elif 'answer' in part:
                            text_parts.append(part['answer'])
                        elif 'content' in part:
                            text_parts.append(part['content'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                    else:
                        text_parts.append(str(part))
                extracted = "\n".join(filter(None, text_parts)).strip()
                logger.debug(f"Extracted text from list content: {extracted[:200]}...")
                return extracted
                
            elif isinstance(content, dict):
                # Try to extract the most relevant fields
                if 'feedback' in content:
                    return str(content['feedback'])
                if 'answer' in content:
                    return str(content['answer'])
                if 'content' in content:
                    return str(content['content'])
                return str(content)
                
            return str(content).strip()
            
        except Exception as e:
            logger.error(f"Failed to extract text from content: {str(e)}\nContent type: {type(content)}\nContent: {str(content)[:200]}")
            return str(content) if content else ""

    def _create_confidence_prompt(self) -> PromptTemplate:
        """Create the confidence scoring prompt template"""
        template = """
You are an expert confidence assessment agent. Your task is to evaluate the confidence score for a generated answer based on the user query, provided chunks, and full page context.

USER QUERY: {user_query}
        
GENERATED ANSWER: {generated_answer}

PROMPT TYPE: {prompt_type}
        
EXPLANATION NEEDED: {explanation_needed}
        
GENERATED EXPLANATION: {generated_explanation}
        
CONTEXT CHUNKS: {chunks}

FULL PAGE CONTEXT: {pages}

CRITICAL RULES FOR CONFIDENCE SCORING:
1. EMPTY OR MINIMAL ANSWERS: If the answer is empty, just whitespace, "N/A", "Not found", or similar non-informative responses, assign confidence score of 0.1 or lower.
2. ANSWER COMPLETENESS: The primary factor is whether the answer adequately addresses the query.
3. SOURCE ALIGNMENT: How well the answer aligns with and is supported by the provided context.
4. EXPLANATION EVALUATION (only if explanation_needed is True):
   - If explanation_needed is True, assess whether the explanation provides precise, verbatim textual evidence from the context (e.g., clause numbers, section titles, or defined terms) that supports the answer.
   - If explanation_needed is False, ignore the explanation and focus solely on the answer.

Evaluate the confidence score (0.0-1.0) based on:
1. Answer Quality and Completeness (70% weight):
   - Does the answer directly and fully address the user's query?
   - For 'verbatim' prompts: Does it extract exact, relevant information as written?
    - For 'summarize' prompts: Does it provide a comprehensive yet concise summary?    
   - Is the answer substantive and informative?

2. Source Coverage and Support (20% weight):
   - How well do the chunks and pages support the answer?
   - Is there sufficient context to justify the answer?

3. Accuracy and Relevance (10% weight):
   - Is the answer factually correct based on the context?
   - Does it stay relevant to the specific question asked?

4. Explanation Quality (only if explanation_needed is True, 10% weight, reducing Source Coverage to 10%):
   - Does the explanation cite specific, verbatim evidence (e.g., "Clause 9.2: 'exact text'") that matches the query and answer?
   - Is the explanation concise, factual, and distinct from the answer?

SCORING GUIDELINES:
- 0.0-0.1: Empty, non-informative, or completely irrelevant answers
- 0.1-0.3: Very poor answers with major gaps or inaccuracies
- 0.3-0.5: Poor answers that partially address the query but with significant issues
- 0.5-0.7: Fair answers that address most of the query with some minor issues
- 0.7-0.85: Good answers that comprehensively address the query with minor gaps
- 0.85-1.0: Excellent answers that fully and accurately address the query

Return your response as a JSON object with this exact format:
{{
    "confidence_score": <float_between_0_and_1>,
    "reasoning": "<brief explanation of the score>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "generated_answer", "prompt_type", "explanation_needed", "generated_explanation", "chunks", "pages"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
    
    def _create_no_chunks_confidence_prompt(self) -> PromptTemplate:
        """Create confidence prompt for when no chunks are available"""
        template = """
You are an expert confidence assessment agent. Your task is to evaluate the confidence score for a generated answer when no context is available.

USER QUERY: {user_query}
        
GENERATED ANSWER: {generated_answer}

PROMPT TYPE: {prompt_type}
        
EXPLANATION NEEDED: {explanation_needed}
        
GENERATED EXPLANATION: {generated_explanation}

CRITICAL RULES FOR CONFIDENCE SCORING:
1. EMPTY OR MINIMAL ANSWERS: If the answer is empty, just whitespace, "N/A", "Not found", or similar non-informative responses, assign confidence score of 0.1 or lower.
2. NO CONTEXT PENALTY: Without source context, maximum confidence is typically 0.6-0.7 unless it's general knowledge.
3. ANSWER SUBSTANCE: Focus primarily on whether the answer provides meaningful information.
4. EXPLANATION EVALUATION (only if explanation_needed is True):
   - If explanation_needed is True, assess whether the explanation provides a concise rationale based on the query’s intent.
   - If explanation_needed is False, ignore the explanation and focus solely on the answer.

Evaluate the confidence score (0.0-1.0) based on:
1. Answer Quality (80% weight):
   - Does the answer provide substantial, meaningful information?
   - Is it directly relevant to the user's query?
   - Does it demonstrate understanding of the question?

2. General Knowledge Accuracy (20% weight):
   - Is the answer consistent with well-established facts?
   - Does it avoid making unsupported claims?

3. Explanation Quality (only if explanation_needed is True, 10% weight, reducing General Knowledge Accuracy to 10%):
   - Does the explanation provide a factual rationale for the answer or absence of information?
   - Is it concise and distinct from the answer?

SCORING GUIDELINES (adjusted for no-context scenario):
- 0.0-0.1: Empty, non-informative, or completely irrelevant answers
- 0.1-0.2: Very minimal answers with little value
- 0.2-0.4: Poor answers that barely address the query
- 0.4-0.6: Fair answers based on general knowledge
- 0.6-0.7: Good general knowledge answers (typical maximum without context)
- 0.7+: Only for exceptional cases with very reliable general knowledge

Return your response as a JSON object with this exact format:
{{
    "confidence_score": <float_between_0_and_1>,
    "reasoning": "<brief explanation of the score>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "generated_answer", "prompt_type", "explanation_needed", "generated_explanation"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
    
    def calculate_confidence(self, user_query: str, generated_answer: str,
                            prompt_type: Optional[str] = None,
                            explanation_needed: bool = False,
                            generated_explanation: Optional[str] = None,
                            chunks: Optional[List[Dict[str, str]]] = None,
                            pages: Optional[Dict[str, str]] = None) -> Dict:
        """Calculate confidence score for the generated answer"""
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        try:
            if not chunks and not pages:
                return self._calculate_confidence_without_chunks(user_query, generated_answer, prompt_type, explanation_needed, generated_explanation)
                
            chunks_text = self._format_chunks(chunks) if chunks else "No relevant chunks found."
            pages_text = self._format_pages(pages) if pages else "No full page context found."
            
            prompt = self.confidence_prompt.format(
                user_query=user_query,
                generated_answer=generated_answer,
                prompt_type=prompt_type or "verbatim",
                explanation_needed=explanation_needed,
                generated_explanation=generated_explanation or "None provided",
                chunks=chunks_text,
                pages=pages_text
            )
            
            response = self.client.invoke([
                SystemMessage(content="You are an expert confidence assessment agent. Return only valid JSON."),
                HumanMessage(content=prompt)
            ])
            
            logger.debug(f"Raw LLM response type: {type(response.content)}, length: {len(str(response.content)) if response.content else 0}")
            text_content = self._extract_text_from_content(response.content)
            if not text_content:
                logger.warning("Empty response from LLM in confidence calculation, using fallback")
                return {"confidence_score": 0.3, "reasoning": "Empty response from LLM service"}
            
            try:
                json.loads(text_content)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from LLM in confidence: {text_content[:100]}..., using fallback")
                return {"confidence_score": 0.3, "reasoning": "Invalid JSON response from LLM service"}
            
            parsed_response = self.parser.parse(text_content)
            logger.debug(f"Confidence response: {parsed_response}")
            
            return parsed_response.model_dump()
                
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error during confidence calculation: {str(e)}")
            raise RuntimeError(f"Failed to calculate confidence score: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during confidence calculation: {str(e)}")
            raise RuntimeError(f"Unexpected error in confidence calculation: {str(e)}") from e
    
    def _calculate_confidence_without_chunks(self, user_query: str, generated_answer: str,
                                            explanation_needed: bool, generated_explanation: Optional[str],prompt_type: Optional[str] = None) -> Dict:
        """Calculate confidence when no chunks are available"""
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        try:
            prompt = self.no_chunks_confidence_prompt.format(
                user_query=user_query,
                generated_answer=generated_answer,
                prompt_type=prompt_type or "verbatim",
                explanation_needed=explanation_needed,
                generated_explanation=generated_explanation or "None provided"
            )
            
            response = self.client.invoke([
                SystemMessage(content="You are an expert confidence assessment agent for no-context scenarios. Penalize empty answers heavily. Return only valid JSON."),
                HumanMessage(content=prompt)
            ])
            
            logger.debug(f"Raw LLM response type: {type(response.content)}, length: {len(str(response.content)) if response.content else 0}")
            text_content = self._extract_text_from_content(response.content)
            if not text_content:
                logger.warning("Empty response from LLM in no-chunks confidence, using fallback")
                return {"confidence_score": 0.3, "reasoning": "Empty response from LLM service"}
            
            try:
                json.loads(text_content)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from LLM in no-chunks confidence: {text_content[:100]}..., using fallback")
                return {"confidence_score": 0.3, "reasoning": "Invalid JSON response from LLM service"}
            
            parsed_response = self.parser.parse(text_content)
            logger.debug(f"No-chunks confidence response: {parsed_response}")
            
            return parsed_response.model_dump()
            
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error during no-chunks confidence calculation: {str(e)}")
            raise RuntimeError(f"Failed to calculate no-chunks confidence score: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during no-chunks confidence calculation: {str(e)}")
            raise RuntimeError(f"Unexpected error in no-chunks confidence calculation: {str(e)}") from e
    
    def _format_chunks(self, chunks: List[Dict[str, str]]) -> str:
        """Format chunks with metadata for confidence assessment"""
        if not chunks:
            return "No relevant context found."
        
        formatted_chunks = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")
            filepath = chunk.get("filepath", "N/A")
            formatted_chunk = f"[Chunk {i}]: Filepath: {filepath}\n{text}"
            formatted_chunks.append(formatted_chunk)
        
        return "\n\n".join(formatted_chunks)
    
    def _format_pages(self, pages: Dict[str, str]) -> str:
        """Format full page context for confidence assessment"""
        if not pages:
            return "No full page context found."
        
        formatted_pages = []
        for page_num, page_text in pages.items():
            if page_text:
                formatted_pages.append(f"[Page {page_num}]: {page_text}")
        
        return "\n\n".join(formatted_pages)

class ValidationAgent:
    """Agent responsible for validating generated answers"""
    
    def __init__(self, api_key: Optional[str] = None, llm_model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-4.1-mini"),
                 reasoning_effort: str = os.getenv("REASONING_EFFORT", "low"),
                 max_completion_tokens: int = int(os.getenv("MAX_RESPONSE_TOKENS", 1000))
        ):
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.api_key:
            raise ValueError("LiteLLM Master Key is required")
        
        self.model = llm_model
        self.reasoning_effort = reasoning_effort
        self.max_completion_tokens = max_completion_tokens
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:4000")
        
        logger.debug(f"Initializing ValidationAgent with model={llm_model}, base_url={base_url}, "
                     f"reasoning_effort={reasoning_effort}, max_tokens={max_completion_tokens}")
        
        params = get_chat_openai_params(self.model, self.reasoning_effort, self.max_completion_tokens, base_url, self.api_key)
        self.client = ChatOpenAI(**params, streaming=False)
        self.parser = PydanticOutputParser(pydantic_object=FeedbackCheckValidationAgent)
        self.validation_prompt = self._create_validation_prompt()
        self.no_chunks_prompt = self._create_no_chunks_prompt()

        self.confidence_agent = ConfidenceAgent(
            api_key=self.api_key,
            llm_model=llm_model,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens
        )
    
    def _extract_text_from_content(self, content: any) -> str:
        """Extract plain text from potentially structured LLM response content."""
        try:
            if content is None:
                return ""
                
            if isinstance(content, str):
                # Try to parse as JSON first if it looks like JSON
                content = content.strip()
                if (content.startswith('{') and content.endswith('}')) or \
                   (content.startswith('[') and content.endswith(']')):
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            # Extract 'feedback' or 'answer' fields if present
                            return parsed.get('feedback', parsed.get('answer', str(parsed)))
                        return str(parsed)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, return as-is
                        pass
                logger.debug(f"Response content is string: {content[:200]}...")
                return content
                
            elif isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif 'feedback' in part:
                            text_parts.append(part['feedback'])
                        elif 'answer' in part:
                            text_parts.append(part['answer'])
                        elif 'content' in part:
                            text_parts.append(part['content'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                    else:
                        text_parts.append(str(part))
                extracted = "\n".join(filter(None, text_parts)).strip()
                logger.debug(f"Extracted text from list content: {extracted[:200]}...")
                return extracted
                
            elif isinstance(content, dict):
                # Try to extract the most relevant fields
                if 'feedback' in content:
                    return str(content['feedback'])
                if 'answer' in content:
                    return str(content['answer'])
                if 'content' in content:
                    return str(content['content'])
                return str(content)
                
            return str(content).strip()
            
        except Exception as e:
            logger.error(f"Failed to extract text from content: {str(e)}\nContent type: {type(content)}\nContent: {str(content)[:200]}")
            return str(content) if content else ""

    def _create_validation_prompt(self) -> PromptTemplate:
        """Create the validation prompt template with emphasis on answer validation"""
        template = """
You are an expert validation agent. Your PRIMARY task is to thoroughly evaluate the ANSWER quality against the user query and provided context.

USER QUERY: {user_query}
        
GENERATED ANSWER: {generated_answer}
        
EXPLANATION NEEDED: {explanation_needed}
        
GENERATED EXPLANATION: {generated_explanation}

PROMPT TYPE: {prompt_type}        
CONTEXT CHUNKS: {chunks}
        
FULL PAGE CONTEXT: {pages}

Evaluate the answer and, if explanation_needed is True, the explanation based on:

1. ANSWER VALIDATION:
   - Completeness: Does the answer fully address all aspects of the user's query?
   - Accuracy: Is the answer factually correct based on the provided context?
   - Relevance: Does the answer directly respond to what was asked?
    - Format Compliance: 
        * For 'verbatim' prompts: Is information extracted exactly as written?
        * For 'summarize' prompts: Is it a proper concise summary?
   - Substance: Does the answer provide meaningful, actionable information?
   - Empty Answer Check: Flag if answer is empty, "N/A", "Not found", or similarly uninformative

2. EXPLANATION VALIDATION (only if explanation_needed is True):
    - Does the explanation extract **precise, verbatim textual evidence** from the transaction documents (e.g., **section names**, **clause numbers**, **schedule numbers**, **defined references**) that supports the answer?
    - Is the explanation **concise**, **factual**, and grounded in **specific terminology** or **references** from the context (not general reasoning)?
    - Is it **distinct** from the answer (i.e., not repeating it)?
    - Is it **clear, targeted, and relevant** to the query — showing exactly where in the contract the support comes from (e.g., “Clause 9.2 under Section 9”)?
    - Does it **avoid** summarizing, paraphrasing, interpreting, or explaining the quote? Only clear reference to where the evidence is found is permitted.   - If the answer is generated, does the explanation provide evidence from the context that directly supports it?
   - If the answer indicates information was not found, does the explanation provide an evidence-based rationale citing specific sections, clauses, or terms searched that lacked the required information?

3. Source Independence:
   - Both answer and explanation (if required) must be self-contained.
   - Do not reference documents, files, chunks, pages, metadata, or tools (e.g., “from the document”, “as per chunk”, “from the PDF”, etc.).
   - Absolutely avoid language like:
       - "according to"
       - "based on the document"
       - "this confirms"
       - "this suggests"
       - "as mentioned above"
       - or any meta, commentary, or word-count related phrases.

CRITICAL VALIDATION RULES:
- If the answer is empty, minimal, or non-informative, this is a MAJOR ISSUE and must be flagged with feedback.
- Prioritize answer quality first. Explanation issues (if explanation_needed is True) are secondary.
- For legal/contract questions with no relevant context, an empty answer may be acceptable.
- Both answer and explanation (if required) must be standalone and should not reference or rely on document structure or metadata.
- If explanation_needed is True and the answer is generated, the explanation must provide supporting evidence from the context; if no evidence is found, flag as a MAJOR ISSUE.
- If explanation_needed is True and the answer indicates information was not found, the explanation must cite specific context searched and explain the absence; generic fallbacks are not acceptable.
- If explanation_needed is False, ignore the explanation entirely.

Final Instruction:
If the answer and explanation (if explanation_needed is True) are completely satisfactory with NO accuracy issues, return exactly: "NO_FEEDBACK"
        
If improvements are needed, provide specific feedback explaining:
- What's wrong with the answer or explanation (if explanation_needed is True) (e.g., incorrect facts, missing details, vague reasoning, or format issues).
- How to improve them (e.g., include specific terms or evidence, correct inaccuracies, or adhere to format).
- What should be changed or added to align with the context and query.

Return your response as a JSON object with this exact format:
{{
    "feedback": "<detailed_feedback_focused_on_answer_or_NO_FEEDBACK>",
    "primary_issue": "<answer|explanation|both|none>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "generated_answer", "explanation_needed", "generated_explanation", "prompt_type", "chunks", "pages"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
    def _create_no_chunks_prompt(self) -> PromptTemplate:
        """Create prompt for when no chunks are available"""
        template = """
You are an expert validation agent. Your PRIMARY task is to evaluate the ANSWER quality when no context is available.

USER QUERY: {user_query}
        
GENERATED ANSWER: {generated_answer}
        
EXPLANATION NEEDED: {explanation_needed}
        
GENERATED EXPLANATION: {generated_explanation}

PROMPT TYPE: {prompt_type}

VALIDATION PRIORITIES:

1. ANSWER VALIDATION:
   - Substance: Does the answer provide meaningful information or is it empty/minimal?
   - Appropriateness: For queries requiring specific context (legal/contracts), is an empty answer appropriate?
   - General Accuracy: Is the answer consistent with general knowledge (if applicable)?
   - Query Alignment: Does it directly address what was asked?

2. EXPLANATION VALIDATION (only if explanation_needed is True):
   - If the answer is generated, does the explanation provide a rationale based on the query's intent?
   - If the answer indicates information was not found, does the explanation explain why no context was available to address the query?
   - Is the explanation concise, factual, and distinct from the answer?

CRITICAL VALIDATION RULES:
- Empty or minimal answers ("N/A", "Not found") may be appropriate for context-dependent queries.
- Focus on answer substance and relevance first.
- For general knowledge queries, expect substantive answers.
- If explanation_needed is True and the answer is generated without context, flag if the explanation lacks rationale for the source of information.
- If explanation_needed is True and the answer indicates information was not found, the explanation must acknowledge the lack of context and its impact on the response.
- If explanation_needed is False, ignore the explanation entirely.

If the answer and explanation (if explanation_needed is True) are completely satisfactory, return exactly: "NO_FEEDBACK"
        
If improvements are needed, provide specific feedback explaining:
- What's wrong with the answer or explanation (if explanation_needed is True) (e.g., incorrect facts, missing details, or format issues).
- How to improve them (e.g., include specific facts or terms, correct inaccuracies, or adhere to format).

Return your response as a JSON object with this exact format:
{{
    "feedback": "<detailed_feedback_focused_on_answer_or_NO_FEEDBACK>",
    "primary_issue": "<answer|explanation|both|none>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "generated_answer", "prompt_type", "explanation_needed", "generated_explanation"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
    
    def validate_answer(self, user_query: str, generated_answer: str,
                       explanation_needed: bool = False,
                       generated_explanation: Optional[str] = None,
                       prompt_type: Optional[str] = None,
                       chunks: Optional[List[Dict[str, str]]] = None,
                       pages: Optional[Dict[str, str]] = None) -> ValidationResult:
        """Validate the generated answer and explanation with confidence score"""
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        try:
            if not chunks and not pages:
                validation_response = self._validate_without_chunks(user_query, generated_answer, explanation_needed, generated_explanation, prompt_type)
            else:
                validation_response = self._validate_with_chunks(user_query, generated_answer, explanation_needed, generated_explanation, prompt_type, chunks, pages)
            
            logger.debug(f"Raw LLM response type: {type(validation_response)}, length: {len(str(validation_response)) if validation_response else 0}")
            text_content = self._extract_text_from_content(validation_response)
            if not text_content:
                logger.warning("Empty validation response from LLM, using fallback")
                return ValidationResult(feedback="NO_FEEDBACK", confidence_score=0.5)
            
            try:
                json.loads(text_content)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Response is not valid JSON: {text_content[:100]}...") from e
            
            parsed_response = self.parser.parse(text_content)
            logger.debug(f"Validation response: {parsed_response}")
            
            confidence_result = self.confidence_agent.calculate_confidence(
                user_query=user_query,
                generated_answer=generated_answer,
                prompt_type=prompt_type,
                explanation_needed=explanation_needed,
                generated_explanation=generated_explanation,
                chunks=chunks,
                pages=pages
            )
            
            return ValidationResult(
                feedback=parsed_response.feedback,
                confidence_score=confidence_result["confidence_score"]
            )
                
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error during validation: {str(e)}")
            raise RuntimeError(f"Failed to validate answer: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during validation: {str(e)}")
            raise RuntimeError(f"Unexpected error in validation: {str(e)}") from e
    
    def _validate_with_chunks(self, user_query: str, generated_answer: str,
                             explanation_needed: bool, generated_explanation: Optional[str],
                             prompt_type: Optional[str],
                             chunks: List[Dict[str, str]], pages: Dict[str, str]) -> str:
        """Validate with chunks and pages available"""
        chunks_text = self._format_chunks(chunks) if chunks else "No relevant chunks found."
        pages_text = self._format_pages(pages) if pages else "No full page context found."
        
        prompt = self.validation_prompt.format(
            user_query=user_query,
            generated_answer=generated_answer,
            explanation_needed=explanation_needed,
            generated_explanation=generated_explanation or "None provided",
            prompt_type=prompt_type or "verbatim",
            chunks=chunks_text,
            pages=pages_text
        )
        
        response = self.client.invoke([
            SystemMessage(content="You are an expert answer validation agent. Return only valid JSON."),
            HumanMessage(content=prompt)
        ])
        
        return response.content
    
    def _validate_without_chunks(self, user_query: str, generated_answer: str,
                                explanation_needed: bool, generated_explanation: Optional[str],
                                prompt_type: Optional[str]) -> str:
        """Special validation when no chunks or pages are available"""
        prompt = self.no_chunks_prompt.format(
            user_query=user_query,
            generated_answer=generated_answer,
            explanation_needed=explanation_needed,
            generated_explanation=generated_explanation or "None provided",
            prompt_type=prompt_type or "verbatim"
        )
        
        response = self.client.invoke([
            SystemMessage(content="You are an expert answer validator for cases with no context. Return only valid JSON."),
            HumanMessage(content=prompt)
        ])
        
        return response.content
    
    def _format_chunks(self, chunks: List[Dict[str, str]]) -> str:
        """Format chunks for validation"""
        if not chunks:
            return "No relevant context found."
        
        formatted_chunks = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")
            filepath = chunk.get("filepath", "N/A")
            formatted_chunk = f"[Context {i}]: Filepath: {filepath}\n{text}"
            formatted_chunks.append(formatted_chunk)
        
        return "\n\n".join(formatted_chunks)
    
    def _format_pages(self, pages: Dict[str, str]) -> str:
        """Format full page context for validation"""
        if not pages:
            return "No full page context found."
        
        formatted_pages = []
        for page_num, page_text in pages.items():
            if page_text:
                formatted_pages.append(f"[Page {page_num}]: {page_text}")
        
        return "\n\n".join(formatted_pages)

class AnswerRefinementAgent:
    """Agent responsible for refining answers and explanations based on feedback"""
    
    def __init__(self, api_key: Optional[str] = None,
                 llm_model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-4.1-mini"),
                 reasoning_effort: str = os.getenv("REASONING_EFFORT", "low"),
                 max_completion_tokens: int = int(os.getenv("MAX_RESPONSE_TOKENS", 1000))
        ):
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.api_key:
            raise ValueError("LiteLLM Master Key is required")
        
        self.model = llm_model
        self.reasoning_effort = reasoning_effort
        self.max_completion_tokens = max_completion_tokens
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:4000")
        
        logger.debug(f"Initializing AnswerRefinementAgent with model={llm_model}, base_url={base_url}, "
                     f"reasoning_effort={reasoning_effort}, max_tokens={max_completion_tokens}")
        
        params = get_chat_openai_params(self.model, self.reasoning_effort, self.max_completion_tokens, base_url, self.api_key)
        self.client = ChatOpenAI(**params, streaming=False)
        self.parser = PydanticOutputParser(pydantic_object=RefinementResult)
        
        self.refinement_prompt = self._create_refinement_prompt()
        self.no_chunks_refinement_prompt = self._create_no_chunks_refinement_prompt()

    def _extract_text_from_content(self, content: any) -> str:
        """Extract plain text from potentially structured LLM response content."""
        try:
            if content is None:
                return ""
                
            if isinstance(content, str):
                # Try to parse as JSON first if it looks like JSON
                content = content.strip()
                if (content.startswith('{') and content.endswith('}')) or \
                   (content.startswith('[') and content.endswith(']')):
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            # Extract 'feedback' or 'answer' fields if present
                            return parsed.get('feedback', parsed.get('answer', str(parsed)))
                        return str(parsed)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, return as-is
                        pass
                logger.debug(f"Response content is string: {content[:200]}...")
                return content
                
            elif isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif 'feedback' in part:
                            text_parts.append(part['feedback'])
                        elif 'answer' in part:
                            text_parts.append(part['answer'])
                        elif 'content' in part:
                            text_parts.append(part['content'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                    else:
                        text_parts.append(str(part))
                extracted = "\n".join(filter(None, text_parts)).strip()
                logger.debug(f"Extracted text from list content: {extracted[:200]}...")
                return extracted
                
            elif isinstance(content, dict):
                # Try to extract the most relevant fields
                if 'feedback' in content:
                    return str(content['feedback'])
                if 'answer' in content:
                    return str(content['answer'])
                if 'content' in content:
                    return str(content['content'])
                return str(content)
                
            return str(content).strip()
            
        except Exception as e:
            logger.error(f"Failed to extract text from content: {str(e)}\nContent type: {type(content)}\nContent: {str(content)[:200]}")
            return str(content) if content else ""

    def _create_refinement_prompt(self) -> PromptTemplate:
        """Create the answer refinement prompt template"""
        template = """
You are an expert answer refinement agent. Your PRIMARY task is to improve the ANSWER based on validation feedback, ensuring it aligns with the user query and provided context.

USER QUERY: {user_query}
        
ORIGINAL ANSWER: {original_answer}
        
EXPLANATION NEEDED: {explanation_needed}
        
ORIGINAL EXPLANATION: {original_explanation}
        
VALIDATION FEEDBACK: {feedback}

PROMPT TYPE: {prompt_type}
        
CONTEXT CHUNKS: {chunks}
        
FULL PAGE CONTEXT: {pages}

REFINEMENT PRIORITIES:
1. ANSWER IMPROVEMENT:
   - Fix completeness, accuracy, relevance, and format issues as specified in the validation feedback.
   - Ensure the answer fully addresses the query’s intent (e.g., extracting specific facts, terms, conditions, or obligations).
   - Make the answer substantial, informative, and directly responsive to the query.
   - Extract information directly from the context, preserving original wording where possible.
   - For 'verbatim': Extract exact information from context
   - For 'summarize': Create concise, comprehensive summaries

2. EXPLANATION IMPROVEMENT (only if explanation_needed is True):
   - Provide precise, verbatim textual evidence from the provided documents (e.g., clause numbers like "Clause 9.2", section titles like "Section 9: Representations", schedule references like "Schedule A", or defined terms like "Purchase Price") that matches the query and supports the improved answer.
   - Mention all relevant details from the context that connect the query and answer, using phrases like "as mentioned in [Clause X.X]" or "as stated in [Section X]".
   - If the improved answer contains substantive information, provide evidence from the context to support it.
   - If the improved answer indicates information was not found (e.g., "Information not found in the provided documents", "not available", "no data"), explain why by citing specific sections, clauses, or terms searched that lacked the required information, or note the absence of relevant content.
   - Keep the explanation concise (50-150 words), factual, and distinct from the answer.
   - Stick strictly to the provided context; do not hallucinate, invent, or assume any information not present in `chunks` or `pages`.
   - Do not mention page numbers, document names, metadata, or tools (e.g., "from the document", "as per chunk").
   - Do not include commentary like "this confirms", "this supports", or "this justifies".
   - Highlight key elements like definitions, conditions, warranties, obligations, or limitations that directly support the answer, using exact contractual language.

3. Address all issues mentioned in the validation feedback, ensuring the answer and explanation (if explanation_needed is True) align with the query’s intent and context.

CRITICAL REFINEMENT RULES:
- If the original answer was empty or minimal and context supports a better answer, provide it.
- If no relevant context is found, an answer indicating absence is acceptable, but the explanation (if explanation_needed is True) must provide an evidence-based rationale for the absence.
- Ensure the answer and explanation (if required) are standalone and do not reference document structure or metadata.
- If explanation_needed is True, always provide a non-empty explanation when an answer is generated, even if minimal evidence is found.
- If explanation_needed is False, set the explanation to an empty string in the response.

Return your response as a JSON object with this exact format:
{{
    "verbatim_answer": "<improved_comprehensive_answer>",
    "explanation": "<improved_explanation_if_needed_or_empty_string>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "original_answer", "explanation_needed", "original_explanation", "feedback", "prompt_type", "chunks", "pages"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )

    def _create_no_chunks_refinement_prompt(self) -> PromptTemplate:
        """Create refinement prompt for when no chunks are available"""
        template = """
You are an expert answer refinement agent for cases with no context. Your PRIMARY task is to improve the ANSWER based on validation feedback, ensuring it aligns with the user query.

USER QUERY: {user_query}
        
ORIGINAL ANSWER: {original_answer}
        
EXPLANATION NEEDED: {explanation_needed}
        
ORIGINAL EXPLANATION: {original_explanation}
        
VALIDATION FEEDBACK: {feedback}

REFINEMENT GUIDELINES:
1. ANSWER IMPROVEMENT:
   - For context-dependent queries (e.g., legal/contracts), an empty or minimal answer (e.g., "Information not found") may be appropriate if no context is available.
   - For general knowledge queries, provide a substantive, accurate answer based on the query’s intent.
   - Ensure the answer directly addresses the query and fixes issues noted in the validation feedback.
   - Follow any format requirements specified in the feedback.

2. EXPLANATION IMPROVEMENT (only if explanation_needed is True):
   - If the improved answer is generated, provide a concise rationale based on the query’s intent, explaining the source of the information (e.g., general knowledge for non-context queries).
   - If the improved answer indicates information was not found, explain why no context was available to address the query.
   - Keep the explanation concise (50-150 words), factual, and distinct from the answer.
   - Stick strictly to the query and feedback; do not hallucinate, invent, or assume any information.
   - Do not mention documents, metadata, or tools.
   - Do not include commentary like "this confirms", "this supports", or "this justifies".
   - If explanation_needed is True, always provide a non-empty explanation when an answer is generated, even if minimal.

CRITICAL REFINEMENT RULES:
- Address all issues in the validation feedback.
- Ensure the answer and explanation (if explanation_needed is True) are standalone and do not reference document structure or metadata.
- If explanation_needed is True and the answer indicates absence, the explanation must acknowledge the lack of context.
- If explanation_needed is False, set the explanation to an empty string in the response.

Return your response as a JSON object with this exact format:
{{
    "verbatim_answer": "<improved_answer>",
    "explanation": "<improved_explanation_if_needed_or_empty_string>"
}}

{format_instructions}
"""
        return PromptTemplate(
            template=template,
            input_variables=["user_query", "original_answer", "explanation_needed", "original_explanation", "feedback", "prompt_type"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
    
    def refine_answer(self, user_query: str, original_answer: str,
                     original_explanation: Optional[str],
                     validation_feedback: str,
                     explanation_needed: bool,
                     prompt_type: Optional[str] = None,
                     chunks: Optional[List[Dict[str, str]]] = None,
                     pages: Optional[Dict[str, str]] = None) -> dict:
        """Refine the answer and explanation based on validation feedback"""
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        if not validation_feedback or validation_feedback.strip() == "NO_FEEDBACK":
            logger.debug("No refinement needed: feedback is empty or 'NO_FEEDBACK'")
            return {
                "verbatim_answer": original_answer,
                "explanation": original_explanation if explanation_needed else ""
            }
            
        try:
            if not chunks and not pages:
                return self._refine_without_chunks(user_query, original_answer, original_explanation, validation_feedback, explanation_needed, prompt_type)
                
            chunks_text = self._format_chunks(chunks) if chunks else "No relevant chunks found."
            pages_text = self._format_pages(pages) if pages else "No full page context found."
            
            prompt = self.refinement_prompt.format(
                user_query=user_query,
                original_answer=original_answer,
                explanation_needed=explanation_needed,
                original_explanation=original_explanation or "None provided",
                feedback=validation_feedback,
                prompt_type=prompt_type or "verbatim",
                chunks=chunks_text,
                pages=pages_text
            )
            
            response = self.client.invoke([
                SystemMessage(content="You are an expert answer refinement agent. Focus primarily on improving answer quality and completeness. Create distinct answer and explanation. Return only valid JSON."),
                HumanMessage(content=prompt)
            ])
            
            logger.debug(f"Raw LLM response type: {type(response.content)}, length: {len(str(response.content)) if response.content else 0}")
            text_content = self._extract_text_from_content(response.content)
            if not text_content:
                raise RuntimeError("Empty text extracted from response content")
            
            # First, try to parse as JSON
            try:
                parsed_json = json.loads(text_content)
                logger.debug(f"Successfully parsed JSON response: {json.dumps(parsed_json, indent=2)[:500]}...")
                
                # If we have a dictionary, try to extract the fields directly
                if isinstance(parsed_json, dict):
                    verbatim_answer = parsed_json.get('verbatim_answer', '')
                    explanation = parsed_json.get('explanation', '')
                    
                    # If we have valid fields, use them
                    if verbatim_answer is not None:
                        return {
                            "verbatim_answer": str(verbatim_answer),
                            "explanation": str(explanation) if explanation_needed and explanation else ""
                        }
                
                # If direct extraction didn't work, try using the parser
                try:
                    parsed_response = self.parser.parse(text_content)
                    logger.debug(f"Successfully parsed response using Pydantic: {parsed_response}")
                    return {
                        "verbatim_answer": parsed_response.verbatim_answer,
                        "explanation": parsed_response.explanation if explanation_needed else ""
                    }
                except (ValueError, ValidationError) as parse_err:
                    logger.warning(f"Pydantic parsing failed, using direct JSON fields: {str(parse_err)}")
                    # Fall through to use the parsed JSON
            
            except json.JSONDecodeError as json_err:
                logger.warning(f"Failed to parse response as JSON: {str(json_err)}\nResponse: {text_content[:200]}...")
                # Fall through to extract text directly
            
            # If we get here, either JSON parsing failed or we couldn't extract the expected fields
            # Try to extract a reasonable response from the text
            logger.info("Attempting to extract answer directly from text response")
            verbatim_answer = text_content.strip()
            
            # If the response is too long, it might contain both answer and explanation
            if len(verbatim_answer) > 200 and '\n' in verbatim_answer:
                parts = verbatim_answer.split('\n', 1)
                verbatim_answer = parts[0].strip()
                explanation = parts[1].strip() if explanation_needed else ""
            else:
                explanation = ""
            
            # Ensure we don't return None values
            verbatim_answer = verbatim_answer or original_answer
            explanation = explanation if explanation_needed else ""
            
            logger.info(f"Extracted answer from text (fallback): {verbatim_answer[:100]}...")
            return {
                "verbatim_answer": verbatim_answer,
                "explanation": explanation
            }
            
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error during answer refinement: {str(e)}")
            raise RuntimeError(f"Failed to refine answer: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during answer refinement: {str(e)}")
            raise RuntimeError(f"Unexpected error in answer refinement: {str(e)}") from e
    
    def _refine_without_chunks(self, user_query: str, original_answer: str,
                              original_explanation: Optional[str], feedback: str,
                              explanation_needed: bool, prompt_type: Optional[str]) -> dict:
        """Special refinement when no chunks are available"""
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        try:
            prompt = self.no_chunks_refinement_prompt.format(
                user_query=user_query,
                original_answer=original_answer,
                explanation_needed=explanation_needed,
                original_explanation=original_explanation or "None provided",
                feedback=feedback,
                prompt_type=prompt_type or "verbatim"
            )
            
            response = self.client.invoke([
                SystemMessage(content="You are an expert answer refinement agent for cases with no context. Focus on answer improvement. Create distinct 'answer' and 'explanation'. Return only valid JSON."),
                HumanMessage(content=prompt)
            ])
            
            logger.debug(f"Raw LLM response type: {type(response.content)}, length: {len(str(response.content)) if response.content else 0}")
            text_content = self._extract_text_from_content(response.content)
            if not text_content:
                raise RuntimeError("Empty text extracted from response content")
            
            # First, try to parse as JSON
            try:
                parsed_json = json.loads(text_content)
                logger.debug(f"Successfully parsed no-chunks JSON response: {json.dumps(parsed_json, indent=2)[:500]}...")
                
                # If we have a dictionary, try to extract the fields directly
                if isinstance(parsed_json, dict):
                    verbatim_answer = parsed_json.get('verbatim_answer', '')
                    explanation = parsed_json.get('explanation', '')
                    
                    # If we have valid fields, use them
                    if verbatim_answer is not None:
                        return {
                            "verbatim_answer": str(verbatim_answer),
                            "explanation": str(explanation) if explanation_needed and explanation else ""
                        }
                
                # If direct extraction didn't work, try using the parser
                try:
                    parsed_response = self.parser.parse(text_content)
                    logger.debug(f"Successfully parsed no-chunks response using Pydantic: {parsed_response}")
                    return {
                        "verbatim_answer": parsed_response.verbatim_answer,
                        "explanation": parsed_response.explanation if explanation_needed else ""
                    }
                except (ValueError, ValidationError) as parse_err:
                    logger.warning(f"Pydantic parsing failed in no-chunks, using direct JSON fields: {str(parse_err)}")
                    # Fall through to use the parsed JSON
            
            except json.JSONDecodeError as json_err:
                logger.warning(f"Failed to parse no-chunks response as JSON: {str(json_err)}\nResponse: {text_content[:200]}...")
                # Fall through to extract text directly
            
            # If we get here, either JSON parsing failed or we couldn't extract the expected fields
            # Try to extract a reasonable response from the text
            logger.info("Attempting to extract answer directly from no-chunks text response")
            verbatim_answer = text_content.strip()
            
            # If the response is too long, it might contain both answer and explanation
            if len(verbatim_answer) > 200 and '\n' in verbatim_answer:
                parts = verbatim_answer.split('\n', 1)
                verbatim_answer = parts[0].strip()
                explanation = parts[1].strip() if explanation_needed else ""
            else:
                explanation = ""
            
            # Ensure we don't return None values
            verbatim_answer = verbatim_answer or original_answer
            explanation = explanation if explanation_needed else ""
            
            logger.info(f"Extracted answer from no-chunks text (fallback): {verbatim_answer[:100]}...")
            return {
                "verbatim_answer": verbatim_answer,
                "explanation": explanation
            }
            
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error during no-chunks refinement: {str(e)}")
            raise RuntimeError(f"Failed to refine answer without chunks: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during no-chunks refinement: {str(e)}")
            raise RuntimeError(f"Unexpected error in no-chunks refinement: {str(e)}") from e
    
    def _format_chunks(self, chunks: List[Dict[str, str]]) -> str:
        """Format chunks for refinement"""
        if not chunks:
            return "No relevant context found."
        
        formatted_chunks = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")
            filepath = chunk.get("filepath", "N/A")
            formatted_chunk = f"[Context {i}]: Filepath: {filepath}\n{text}"
            formatted_chunks.append(formatted_chunk)
        
        return "\n\n".join(formatted_chunks)
    
    def _format_pages(self, pages: Dict[str, str]) -> str:
        """Format full page context for refinement"""
        if not pages:
            return "No full page context found."
        
        formatted_pages = []
        for page_num, page_text in pages.items():
            if page_text:
                formatted_pages.append(f"[Page {page_num}]: {page_text}")
        
        return "\n\n".join(formatted_pages)

class ValidationSystem:
    """Main validation system that orchestrates the iterative improvement process with confidence scoring"""
    
    def __init__(self, llm_model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-4.1-mini"),
                 reasoning_effort: str = os.getenv("REASONING_EFFORT", "low"),
                 max_iterations: int = int(os.getenv("VALIDATION_MAX_ITERATIONS", 3)),
                 max_completion_tokens: int = int(os.getenv("MAX_RESPONSE_TOKENS", 1000))
    ):
        logger.debug(f"Initializing ValidationSystem with model={llm_model}, reasoning_effort={reasoning_effort}, "
                     f"max_iterations={max_iterations}, max_tokens={max_completion_tokens}")
        
        self.validation_agent = ValidationAgent(
            llm_model=llm_model,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens
        )
        self.refinement_agent = AnswerRefinementAgent(
            llm_model=llm_model,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens
        )
        self.confidence_agent = ConfidenceAgent(
            llm_model=llm_model,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens
        )
        self.max_iterations = max_iterations
        self.iteration_results: List[IterationResult] = []
        self.confidence_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", 0.7))
        self.min_confidence_for_explanation = float(os.getenv("MIN_CONFIDENCE_FOR_EXPLANATION", 0.6))
    
    def check_confidence_score(self, confidence_score: float, iteration: int = 0) -> bool:
        """Check if confidence score meets threshold and log appropriate messages"""
        if confidence_score < self.confidence_threshold:
            if confidence_score <= 0.2:
                logger.warning(f"Very low confidence score detected: {confidence_score:.2f} (iteration {iteration}) - Answer may be empty or severely inadequate")
            else:
                logger.warning(f"Low confidence score detected: {confidence_score:.2f} (iteration {iteration}) - Below threshold: {self.confidence_threshold}")
            return False
        else:
            logger.info(f"Confidence score: {confidence_score:.2f} (iteration {iteration}) - Above threshold: {self.confidence_threshold}")
            return True
    
    def validate_and_improve(self, user_query: str, initial_answer: str,
                           initial_explanation: Optional[str] = None,
                           explanation_needed: bool = False,
                           prompt_type: Optional[str] = None,
                           chunks: Optional[List[Dict[str, str]]] = None,
                           pages: Optional[Dict[str, str]] = None,
                           max_iterations: Optional[int] = None) -> Dict:
        """
        Main method to validate and iteratively improve the answer and explanation with confidence scoring
        
        Args:
            user_query: The original user question
            initial_answer: The initially generated answer
            initial_explanation: The initially generated explanation (if any)
            explanation_needed: Whether an explanation is required
            prompt_type: "summarize" or "verbatim" to control response style
            chunks: Optional list of chunk dictionaries with text and metadata
            pages: Optional dictionary of page numbers to full page text
            max_iterations: Override default max iterations for this call
            
        Returns:
            Dictionary containing final answer, explanation, confidence score, and iteration history
        """
        if prompt_type not in ["verbatim", "summarize", None]:
            logger.warning(f"Invalid prompt_type: {prompt_type}, defaulting to 'verbatim'")
            prompt_type = "verbatim"
        current_max_iterations = max_iterations if max_iterations is not None else self.max_iterations
        logger.info(f"Starting validation and improvement process for prompt_type: {prompt_type or 'verbatim'}, explanation_needed: {explanation_needed}, max_iterations: {current_max_iterations}")
        logger.info(f"Initial answer length: {len(initial_answer)} characters")
        
        current_answer = initial_answer
        current_explanation = initial_explanation
        self.iteration_results = []
        
        try:
            # Initial confidence check
            initial_confidence_result = self.confidence_agent.calculate_confidence(
                user_query=user_query,
                generated_answer=current_answer,
                explanation_needed=explanation_needed,
                generated_explanation=current_explanation,
                prompt_type=prompt_type,
                chunks=chunks,
                pages=pages
            )
            initial_confidence_result = ConfidenceResult(**initial_confidence_result)
            initial_confidence_score = initial_confidence_result.confidence_score
            
            logger.info(f"Initial confidence: {initial_confidence_score:.2f} - {initial_confidence_result.reasoning}")
            
            # Check if we should skip improvement loop
            skip_improvement = initial_confidence_score < 0.3 or initial_confidence_score >= 0.90
            if skip_improvement:
                logger.info(f"Skipping improvement loop due to initial confidence {initial_confidence_score:.2f} (below 0.3 or >= 0.90)")
                final_confidence_score = initial_confidence_score
                final_explanation = ""  # Changed to empty string
                if explanation_needed:
                    if final_confidence_score >= self.min_confidence_for_explanation:
                        final_explanation = current_explanation
                    else:
                        final_explanation = "Insufficient information available to provide a reliable explanation for this answer."
                        logger.warning(f"Low confidence ({final_confidence_score:.2f}) - providing fallback explanation")
                return {
                    "final_answer": current_answer,
                    "final_answer_explanation": final_explanation,
                    "final_confidence_score": final_confidence_score,
                    "confidence_threshold_met": self.check_confidence_score(final_confidence_score, "final"),
                    "initial_confidence_score": initial_confidence_score,
                    "confidence_improvement": 0.0,
                    "total_iterations": 0,
                    "iteration_history": []
                }
            
            for iteration in range(1, current_max_iterations + 1):
                logger.info(f"Starting iteration {iteration}")
                
                validation_result = self.validation_agent.validate_answer(
                    user_query=user_query,
                    generated_answer=current_answer,
                    explanation_needed=explanation_needed,
                    generated_explanation=current_explanation,
                    prompt_type=prompt_type,
                    chunks=chunks,
                    pages=pages
                )
                
                if not self.check_confidence_score(validation_result.confidence_score, iteration):
                    logger.warning(f"Stopping iterations due to low confidence score in iteration {iteration}")
                    iteration_result = IterationResult(
                        iteration=iteration,
                        original_answer=current_answer,
                        original_explanation=current_explanation,
                        validation_result=validation_result,
                        improved_answer=current_answer,
                        improved_explanation=current_explanation,
                        timestamp=self._get_timestamp(),
                        confidence_score=validation_result.confidence_score
                    )
                    self.iteration_results.append(iteration_result)
                    break
                
                iteration_result = IterationResult(
                    iteration=iteration,
                    original_answer=current_answer,
                    original_explanation=current_explanation,
                    validation_result=validation_result,
                    improved_answer="",
                    improved_explanation=None,
                    timestamp=self._get_timestamp(),
                    confidence_score=validation_result.confidence_score
                )
                
                needs_refinement = (
                    validation_result.feedback and
                    validation_result.feedback.strip() != "NO_FEEDBACK" and
                    validation_result.feedback.strip() != ""
                )
                
                if needs_refinement:
                    logger.info(f"Refinement needed in iteration {iteration}")
                    logger.debug(f"Validation feedback: {validation_result.feedback[:200]}...")
                    
                    refined_response = self.refinement_agent.refine_answer(
                        user_query=user_query,
                        original_answer=current_answer,
                        original_explanation=current_explanation,
                        validation_feedback=validation_result.feedback,
                        explanation_needed=explanation_needed,
                        prompt_type=prompt_type,
                        chunks=chunks,
                        pages=pages
                    )
                    
                    iteration_result.improved_answer = refined_response["verbatim_answer"]
                    iteration_result.improved_explanation = refined_response["explanation"]
                    current_answer = refined_response["verbatim_answer"]
                    current_explanation = refined_response["explanation"]
                    
                    logger.info(f"Refined answer length: {len(current_answer)} characters")
                else:
                    logger.info(f"No refinement needed in iteration {iteration}")
                    iteration_result.improved_answer = current_answer
                    iteration_result.improved_explanation = current_explanation
                    self.iteration_results.append(iteration_result)
                    break
                
                self.iteration_results.append(iteration_result)
                
                if iteration == current_max_iterations:
                    logger.info(f"Reached maximum iterations ({current_max_iterations})")
                    break
            
            final_confidence_result = self.confidence_agent.calculate_confidence(
                user_query=user_query,
                generated_answer=current_answer,
                explanation_needed=explanation_needed,
                generated_explanation=current_explanation,
                prompt_type=prompt_type,
                chunks=chunks,
                pages=pages
            )
            final_confidence_result = ConfidenceResult(**final_confidence_result)
            final_confidence_score = final_confidence_result.confidence_score
            final_meets_threshold = self.check_confidence_score(final_confidence_score, "final")
            
            logger.info(f"Final confidence reasoning: {final_confidence_result.reasoning}")
            
            final_explanation = ""  # Changed to empty string
            if explanation_needed:
                if final_confidence_score >= self.min_confidence_for_explanation:
                    final_explanation = current_explanation
                else:
                    final_explanation = "Insufficient information available to provide a reliable explanation for this answer."
                    logger.warning(f"Low confidence ({final_confidence_score:.2f}) - providing fallback explanation")
            
            logger.info(f"Validation completed after {len(self.iteration_results)} iterations")
            logger.info(f"Final answer length: {len(current_answer)} characters")
            logger.info(f"Final confidence score: {final_confidence_score:.2f}")
            logger.info(f"Confidence threshold met: {final_meets_threshold}")
            
            return {
                "final_answer": current_answer,
                "final_answer_explanation": final_explanation,
                "final_confidence_score": final_confidence_score,
                "confidence_threshold_met": final_meets_threshold,
                "initial_confidence_score": initial_confidence_score,
                "confidence_improvement": final_confidence_score - initial_confidence_score,
                "total_iterations": len(self.iteration_results),
                "iteration_history": [
                    {
                        "iteration": result.iteration,
                        "original_answer": result.original_answer,
                        "original_explanation": result.original_explanation,
                        "validation_feedback": result.validation_result.feedback,
                        "improved_answer": result.improved_answer,
                        "improved_explanation": result.improved_explanation,
                        "timestamp": result.timestamp,
                        "confidence_score": result.confidence_score
                    }
                    for result in self.iteration_results
                ]
            }
        
        except (ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"Error in validate_and_improve: {str(e)}")
            raise RuntimeError(f"Failed to validate and improve answer: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error in validate_and_improve: {str(e)}")
            raise RuntimeError(f"Unexpected error in validate_and_improve: {str(e)}") from e
    
    def _get_timestamp(self) -> str:
        """Generate a timestamp for iteration results"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")