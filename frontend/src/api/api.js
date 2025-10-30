import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL

export const upload_file = async (projectData, files) => {
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


export const getTemplates = async (template_name) => {
  try {
    const response = await axios.post(
      `${API_URL}/project/process-template`,
      { template_name: template_name },
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
  
// Fetch available template names
export const getTemplateNames = async () => {
  try {
    const response = await axios.get(`${API_URL}/project/get-templates`);
    return response.data;
  } catch (error) {
    console.error("Error fetching template names:", error);
    throw error;
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
    const projectsMap = JSON.parse(sessionStorage.getItem("projects_map")) || {};
    return projectsMap[projectName] || null;
  };
  
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

// Fetch list of projects with pagination
export const getProjects = async (skip = 0, limit = 100) => {
  try {
    const response = await axios.get(`${API_URL}/project`, {
      params: { skip, limit },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching projects:", error);
    throw error;
  }
};

// Upload additional documents to an existing project
export const uploadDocuments = async (projectId, files, fieldNames = [], templateName = "spa_fields") => {
  try {
    const formData = new FormData();
    // Append files (can be multiple)
    files.forEach((file) => {
      formData.append("files", file);
    });
    // Append field names as a JSON array string
    formData.append("field_names", JSON.stringify(fieldNames || []));
    // Append template name (backend default used if not provided)
    if (templateName) {
      formData.append("template_name", templateName);
    }

    const response = await axios.post(`${API_URL}/project/${projectId}/documents`, formData, {
      headers: {
        accept: "application/json",
        "Content-Type": "multipart/form-data",
      },
    });
    return response.data;
  } catch (error) {
    console.error("Error uploading documents:", error);
    throw error;
  }
};

// Regenerate a document's extraction for specified fields
export const regenerateDocument = async (projectId, documentId, fieldNames = []) => {
  try {
    const params = {};
    if (Array.isArray(fieldNames) && fieldNames.length) {
      params.field_names = fieldNames.join(',');
    }
    const url = `${API_URL}/project/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/regenerate`;
    const response = await axios.post(url, null, {
      params,
      headers: { accept: "application/json" },
    });
    return response.data;
  } catch (error) {
    console.error("Error regenerating document:", error);
    throw error;
  }
};