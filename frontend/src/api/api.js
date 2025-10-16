import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL

export const upload_file = async (projectData, files) => {
    console.log(projectData , files)
    try {
      const formData = new FormData();

      formData.append("project_name", projectData.project_name);
      formData.append("template_name", projectData.template_name || "spa_fields");
  
     
      // Send the selected field keys from the caller
      formData.append("field_names", JSON.stringify(projectData.field_names || []));

  
   
      files.forEach((file) => {
        formData.append("files", file); 

      });
    
      const response = await axios.post(`${API_URL}/project/submit`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
  
      return response.data; 
    } catch (error) {
      console.error("Error uploading files:", error);
      throw error;
    }
  };

// Get project details including documents list and statuses
export const getProjectDetails = async (projectId) => {
    try {
      const response = await axios.get(`${API_URL}/project/${projectId}`);
      return response.data;
    } catch (error) {
      console.error("Error fetching project details:", error);
      throw error;
    }
  };

export const get_document_status = async (project_id) => {
    try {
      const response = await axios.get(`${API_URL}/project/${project_id}/documents`);
  
      return response.data;
    } catch (error) {
      console.error("Error fetching document status:", error);
      throw error; 
    }
  };

export const getDocumentResults = async (projectId) => {
    try {
      const response = await axios.get(
        `${API_URL}/project/${projectId}/results`
      );
      return response.data;
    } catch (error) {
      console.error("Error fetching document results:", error);
      throw error;
    }
  };


export const getTemplates = async (template_name = "spa_fields") => {
    try {
      const response = await axios.post(
        `${API_URL}/project/process-template`,
        { template_name },
        {
          headers: {
            "Content-Type": "application/json",
          },
        }
      );
      return response.data;
    } catch (error) {
      console.error("Error fetching templates:", error);
    }
  };
  

export const updateDocumentResult = async (projectId, docId, fieldName, value) => {
    try {
      const payload = { field_name: fieldName, value };
      const response = await axios.put(
        `${API_URL}/project/${projectId}/document/${projectId}_${docId}/results`,
        payload
      );
      return response.data;
    } catch (error) {
      console.error("Error updating document result:", error);
      throw error;
    }
  };


export const getProjectIdByName = (projectName) => {
    const projectsMap = JSON.parse(localStorage.getItem("projects_map")) || {};
    return projectsMap[projectName] || null;
  };
  

  // Add this function to handle Excel export

// New API for updating a single field result on a document
export const updateFieldResult = async (documentId, fieldName, updates) => {
  try {
    const url = `${API_URL}/project/field-result/${encodeURIComponent(documentId)}/${encodeURIComponent(fieldName)}`;
    const response = await axios.put(
      url,
      updates,
      {
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
      }
    );
    return response.data;
  } catch (error) {
    console.error("Error updating field result:", error);
    throw error;
  }
};