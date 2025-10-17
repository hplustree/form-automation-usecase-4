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
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from "@mui/material";
import {
  Close as CloseIcon,
} from "@mui/icons-material";
import { LuUpload } from "react-icons/lu";
import { upload_file, getTemplates, getTemplateNames } from "../api/api";

const CreateProjectModal = ({ open, onClose, onCreateProject }) => {
  const [projectName, setProjectName] = useState("");
  // Flat list of fields from API: { id, label, checked }
  const [fields, setFields] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [templateName, setTemplateName] = useState("");
  const [templateOptions, setTemplateOptions] = useState([]);
  const [templates, setTemplates] = useState([]);
const [selectedTemplate, setSelectedTemplate] = useState("");


  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const allChecked = fields.length > 0 && fields.every((i) => i.checked);
  const someChecked = fields.some((i) => i.checked) && !allChecked;

  const mergeFiles = (prevFiles, newFiles) => {
    const map = new Map();
    [...prevFiles, ...newFiles].forEach((f) => {
      const key = `${f.name}_${f.size}_${f.lastModified}`;
      if (!map.has(key)) map.set(key, f);
    });
    return Array.from(map.values());
  };

  const handleFieldToggle = (itemId) => {
    setFields((prev) =>
      prev.map((item) =>
        item.id === itemId ? { ...item, checked: !item.checked } : item
      )
    );
  };

  const handleToggleAll = (checked) => {
    setFields((prev) => prev.map((item) => ({ ...item, checked })));
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
    setUploadedFiles((prev) => mergeFiles(prev, files));
    console.log("Files dropped:", files);
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setUploadedFiles((prev) => mergeFiles(prev, files));
    // allow selecting the same file again by resetting the input value
    e.target.value = null;
    console.log("Files selected:", files);
  };

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
        template_name: selectedTemplate,
      };
  
      // Pre-seed by project name for immediate UI rendering on Dashboard
      // This lets the Results table appear instantly even before the upload finishes
      try {
        // Save selected fields keyed by project name
        const fieldsByName = JSON.parse(localStorage.getItem('project_fields_map_by_name')) || {};
        fieldsByName[projectName] = selectedFieldNames;
        localStorage.setItem('project_fields_map_by_name', JSON.stringify(fieldsByName));

        // Seed placeholder results ("Processing") for each selected file keyed by project name
        const seedByName = uploadedFiles.map((f, idx) => {
          const resultObj = {};
          selectedFieldNames.forEach((fn) => {
            resultObj[fn] = { value: 'Processing' };
          });
          return {
            id: `temp_${idx}_${Date.now()}`,
            doc_id: null,
            fileName: f.name,
            docName: f.name,
            results: resultObj,
          };
        });
        const seedsMapByName = JSON.parse(localStorage.getItem('pending_results_seed_by_name')) || {};
        seedsMapByName[projectName] = seedByName;
        localStorage.setItem('pending_results_seed_by_name', JSON.stringify(seedsMapByName));
      } catch (e) {
        console.warn('Failed to pre-seed by project name', e);
      }

      if (uploadedFiles.length > 0) {
        const response = await upload_file(projectData, uploadedFiles);
        storeProjectIdByName(projectName, response.project_id);

        // Persist selected fields for this project so Results table can show headers immediately
        try {
          const fieldsMap = JSON.parse(localStorage.getItem('project_fields_map')) || {};
          fieldsMap[response.project_id] = selectedFieldNames;
          localStorage.setItem('project_fields_map', JSON.stringify(fieldsMap));
        } catch (e) {
          console.warn('Failed to save project fields to localStorage', e);
        }

        // Seed placeholder results so Dashboard can render a table instantly
        try {
          const seed = uploadedFiles.map((f, idx) => {
            const resultObj = {};
            selectedFieldNames.forEach((fn) => {
              resultObj[fn] = { value: 'Processing' };
            });
            return {
              id: `temp_${idx}_${Date.now()}`,
              doc_id: null,
              fileName: f.name,
              docName: f.name,
              results: resultObj,
            };
          });
          const seedsMap = JSON.parse(localStorage.getItem('pending_results_seed')) || {};
          seedsMap[response.project_id] = seed;
          localStorage.setItem('pending_results_seed', JSON.stringify(seedsMap));
          // Optional: cleanup name-based seed now that we have a real project id
          try {
            const seedsMapByName = JSON.parse(localStorage.getItem('pending_results_seed_by_name')) || {};
            if (seedsMapByName[projectName]) {
              delete seedsMapByName[projectName];
              localStorage.setItem('pending_results_seed_by_name', JSON.stringify(seedsMapByName));
            }
            const fieldsByName = JSON.parse(localStorage.getItem('project_fields_map_by_name')) || {};
            if (fieldsByName[projectName]) {
              delete fieldsByName[projectName];
              localStorage.setItem('project_fields_map_by_name', JSON.stringify(fieldsByName));
            }
          } catch (e) {
            console.warn('Failed to cleanup name-based pre-seed', e);
          }
        } catch (e) {
          console.warn('Failed to seed pending results to localStorage', e);
        }

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
    setUploadedFiles([]);
    onClose();
  };

  const handleDialogClose = (...args) => {
    setProjectName("");
    setFields((prev) => prev.map((i) => ({ ...i, checked: false })));
    setUploadedFiles([]);
    setTemplateName("");
    setSelectedTemplate("");
    onClose && onClose(...args);
  };

  // Fetch template names when modal opens
  useEffect(() => {
    if (!open) return;
    const fetchTemplateNames = async () => {
      try {
        const data = await getTemplateNames();
        let names = [];
        if (Array.isArray(data)) names = data;
        else if (data && Array.isArray(data.templates)) names = data.templates;
        else if (data && data.data && Array.isArray(data.data)) names = data.data;
        setTemplateOptions(names);
      } catch (e) {
        console.error("Failed to fetch template names", e);
      }
    };
    fetchTemplateNames();
  }, [open]);

  // Fetch fields when template changes
  useEffect(() => {
    if (!open || !templateName) return;
    const fetchFieldsForTemplate = async () => {
      try {
        const res = await getTemplates(templateName);
        if (res && res.fields) {
          const entries = Object.entries(res.fields);
          const mapped = entries.map(([id, label]) => ({ id, label, checked: false }));
          setFields(mapped);
        } else {
          setFields([]);
        }
      } catch (e) {
        console.error("Failed to fetch template fields", e);
        setFields([]);
      }
    };
    fetchFieldsForTemplate();
  }, [open, templateName]);

  // If no template is selected, ensure fields list is empty
  useEffect(() => {
    if (!open) return;
    if (!templateName) {
      setFields([]);
    }
  }, [open, templateName]);

  // Keep templateName in sync with the user's selection
  useEffect(() => {
    if (selectedTemplate) {
      setTemplateName(selectedTemplate);
    }
  }, [selectedTemplate]);


  useEffect(() => {
    const fetchTemplateNames = async () => {
      try {
        const res = await getTemplateNames();
        
        // The API returns an array directly: [{"code":"spa_field","name":"Share Purchase Agreement"}]
        if (res && Array.isArray(res)) {
          setTemplates(res);
          localStorage.setItem("cached_templates", JSON.stringify(res));
        }
      } catch (e) {
        console.error("Failed to fetch template names", e);
      }
    };
  
    if (open) {
      fetchTemplateNames();
    }
  }, [open]);
  

  return (
    <Dialog
      open={open}
      onClose={handleDialogClose}
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
        <IconButton onClick={handleDialogClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        <Grid container spacing={3}>
          {/* Project Name */}
          <Grid item xs={12} width={"100%"} >
            <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
              Project Name
            </Typography>
            <TextField
              fullWidth
              placeholder="e.g., Q1 2024 Invoices"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              variant="outlined"
              size="small"
            />
          </Grid>
          </Grid>

        <Grid container spacing={3}>
          
        <Grid item xs={12} width={"100%"} mt={2} mb={2}>
            <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
              Template
            </Typography>
            <TextField
              fullWidth
              select
              value={selectedTemplate}
              onChange={(e) => { setSelectedTemplate(e.target.value); setTemplateName(e.target.value); }}
              variant="outlined"
              SelectProps={{ native: true }}
              size="small"
            >
             <option value="">Select a template</option>
                {templates.map((template, index) => (
                  <option key={index} value={template.code}>
                    {template.code}
                  </option>
                ))}
            </TextField>
          </Grid>
        </Grid> 

          

          <Grid container spacing={3} sx={{ mt: 1 }}>
        {/* Upload Documents */}
          <Grid item xs={12}>
            <Typography
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: 600 }}
            >
              {/* Upload Documents */}
              {templates.find(t => t.code === selectedTemplate)?.name || "Upload Documents"}
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
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={allChecked}
                        indeterminate={someChecked}
                        onChange={(e) => handleToggleAll(e.target.checked)}
                        size="small"
                      />
                    }
                    label="Select All"
                    sx={{ ml: 1 }}
                  />
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
        {/* </Grid> */}
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