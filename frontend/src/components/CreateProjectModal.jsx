import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  Typography,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Grid,
  IconButton,
  Paper,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import {
  Close as CloseIcon,
} from "@mui/icons-material";
import { LuUpload } from "react-icons/lu";
import { upload_file, getTemplates } from "../api/api";

const CreateProjectModal = ({ open, onClose, onCreateProject }) => {
  const [projectName, setProjectName] = useState("");
  // Flat list of fields from API: { id, label, checked }
  const [fields, setFields] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const handleFieldToggle = (itemId) => {
    setFields((prev) =>
      prev.map((item) =>
        item.id === itemId ? { ...item, checked: !item.checked } : item
      )
    );
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    setUploadedFiles(files);
    console.log("Files dropped:", files);
  };

  // const FileUpload = ({ files, onFilesSelected }) => {
  //   const handleFileChange = (event) => {
  //     const selectedFiles = Array.from(event.target.files);
  //     onFilesSelected([...files, ...selectedFiles]);
  //   };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setUploadedFiles(files);
    console.log("Files selected:", files);
  };

  // const handleCreate = () => {
  //   if (projectName.trim()) {
  //     const newProject = {
  //       id: Date.now(),
  //       name: projectName,
  //       documentCount: 0,
  //       isActive: false,
  //       type: "custom",
  //     };

  //     onCreateProject(newProject);
  //     setProjectName("");
  //     setKeyPoints(keyPointOptions);
  //     onClose();
  //   }
  // };

  const storeProjectIdByName = (projectName, projectId) => {
    const projectsMap = JSON.parse(localStorage.getItem("projects_map")) || {};
  
    projectsMap[projectName] = projectId;
  
    localStorage.setItem("projects_map", JSON.stringify(projectsMap));
  };


  const handleCreate = async () => {
    if (!projectName.trim()) {
      // alert("Please enter a project name.");
      return;
    }
    try {
      const selectedFieldNames = fields.filter(item => item.checked).map(item => item.id);
  
      if (selectedFieldNames.length === 0) {
        // alert("Please select at least one field.");
        return;
      }
  
      const projectData = {
        project_name: projectName,
        field_names: selectedFieldNames,
        template_name: "spa_fields",
      };
  
      if (uploadedFiles.length > 0) {
        const response = await upload_file(projectData, uploadedFiles);
        storeProjectIdByName(projectName, response.project_id);

        console.log("Upload response:", response);
        // alert("Project created and files uploaded successfully!");
      } else {
        // alert("Project created! No files were uploaded.");
      }
  
      const newProject = {
        id: Date.now(),
        name: projectName,
        documentCount: uploadedFiles.length,
        isActive: false,
        type: "custom",
      };
      onCreateProject(newProject);
  
      // 5️⃣ Reset modal state
      setProjectName("");
      setFields((prev) => prev.map((i) => ({ ...i, checked: false })));
      setUploadedFiles([]);
      onClose();
    } catch (error) {
      console.error("Error creating project:", error);
      // alert("Failed to create project. Check console for details.");
    }
  };

  const handleCancel = () => {
    setProjectName("");
    setFields((prev) => prev.map((i) => ({ ...i, checked: false })));
    onClose();
  };

  // useEffect
  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const res = await getTemplates("spa_fields");
        if (res && res.fields) {
          const entries = Object.entries(res.fields);
          const mapped = entries.map(([id, label]) => ({ id, label, checked: false }));
          setFields(mapped);
        }
      } catch (e) {
        console.error("Failed to fetch template fields", e);
      }
    };
    if (open) {
      fetchTemplates();
    }
  }, [open]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      fullScreen={isMobile}
    >
      <DialogTitle
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          pb: 2,
        }}
      >
        <Box>
          <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
            Create New Project
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Configure your project name, upload documents, and select key points
            to extract
          </Typography>
        </Box>
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        <Grid container spacing={3}>
          {/* Project Name */}
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            Project Name
          </Typography>
          <TextField
            fullWidth
            placeholder="e.g., Q1 2024 Invoices"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            variant="outlined"
          />
          
          {/* Upload Documents */}
          <Grid item xs={12}>
            <Typography
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: 600 }}
            >
              Upload Documents
            </Typography>

            <Paper
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              sx={{
                border: "1px dashed",
                borderColor: dragOver ? "primary.main" : "divider",
                borderRadius: 1,
                p: 2,
                height: 250,
                textAlign: "center",
                cursor: "pointer",
                backgroundColor: dragOver ? "action.hover" : "background.paper",
                transition: "all 0.2s ease-in-out",
                "&:hover": {
                  backgroundColor: "action.hover",
                  borderColor: "primary.main",
                  transform: "translateY(-2px)",
                },
              }}
              onClick={() => document.getElementById("file-upload").click()}
            >
              <LuUpload
                size={48}
                color={dragOver ? "#1976d2" : "#9e9e9e"}
                style={{
                  marginBottom: 16,
                  transition: "color 0.2s ease-in-out",
                }}
              />
              <Typography variant="h6" gutterBottom>
                Drop documents here or click to browse
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Supports PDF, DOCX, TXT files up to 10MB each
              </Typography>
              <input
                id="file-upload"
                type="file"
                multiple
                accept=".pdf,.docx,.txt"
                style={{ display: "none" }}
                onChange={handleFileSelect}
              />
            </Paper>

            {uploadedFiles.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography
                  variant="subtitle2"
                  gutterBottom
                  sx={{ fontWeight: 600 }}
                >
                  Selected files:
                </Typography>
                <Paper
                  sx={{
                    // p: 2,
                    borderRadius: 2,
                    border: 1,
                    borderColor: "divider",
                    backgroundColor: "background.paper",
                    width: "27rem",
                  }}
                >
                  {uploadedFiles.map((file, index) => (
                    <Box
                      key={index}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        p: 2,
                        borderBottom:
                          index < uploadedFiles.length - 1
                            ? "1px solid"
                            : "none",
                        gap: 2,
                        // borderColor: "divider",
                      }}
                    >
                      <Box
                        component="span"
                        sx={{
                          mr: 1,
                          color: "text.secondary",
                        }}
                      >
                        📄
                      </Box>
                      <Typography
                        variant="body2"
                        sx={{
                          flexGrow: 1,
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                        }}
                      >
                        {file.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(file.size / 1024).toFixed(2)} KB
                      </Typography>
                    </Box>
                  ))}
                </Paper>
              </Box>
            )}
          </Grid>

          {/* Fields Selection */}
          <Grid item xs={12} md={6} width={"45%"}>
            <Typography
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: 600 }}
            >
              Select Fields to Extract
            </Typography>

            <Box
              sx={{
                maxHeight: 300,
                overflowY: "auto",
                border: 1,
                borderColor: "divider",
                borderRadius: 2,
                p: 2,
              }}
            >
              {fields.length > 0 ? (
                <FormGroup>
                  {fields.map((item) => (
                    <FormControlLabel
                      key={item.id}
                      control={
                        <Checkbox
                          checked={item.checked}
                          onChange={() => handleFieldToggle(item.id)}
                          size="small"
                        />
                      }
                      label={item.label}
                      sx={{ ml: 1 }}
                    />
                  ))}
                </FormGroup>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No fields available.
                </Typography>
              )}
            </Box>
          </Grid>
        </Grid>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={handleCancel}  sx={({
              palette,
            }) => ({
              color: palette.primary.main,
              border: `1px solid ${palette.primary.main}`,
              "&:hover": {
                backgroundColor: palette.action.hover,
                borderColor: palette.primary.dark,
                color: palette.primary.dark,
              },
              fontWeight: 600,
              textTransform: "none",
              px: 2,
              py: 0.75,
            })}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={!projectName.trim()}
          sx={{
            backgroundColor: "#1976d2",
            "&:hover": {
              backgroundColor: "#1565c0",
            },
          }}
        >
          Create Project
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CreateProjectModal;
