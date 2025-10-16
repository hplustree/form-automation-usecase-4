import React, { useEffect, useState } from "react";
import { alpha } from "@mui/material/styles";
import {
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  LinearProgress,
  Chip,
  IconButton,
  useTheme,
  Button,
  CircularProgress,
  Divider,
  Tooltip,
  TextField,
  Snackbar,
  Alert
} from "@mui/material";
import {
  Description as DescriptionIcon,
  UploadOutlined,
} from "@mui/icons-material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import InsertDriveFileOutlinedIcon from '@mui/icons-material/InsertDriveFileOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import DownloadIcon from '@mui/icons-material/Download';
import { get_document_status, getDocumentResults, getProjectDetails, updateFieldResult } from "../api/api";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box >{children}</Box>}
    </div>
  );
};

// Helper function to format field names for display
const formatFieldName = (fieldName) => {
  return fieldName
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};


 const exportToExcel = (extractionResults, tableHeaders, projectName) => {
  if (!extractionResults.length || !tableHeaders.length) return;

  try {
    // Create CSV content
    const headers = ['File Name', ...tableHeaders.map(header => formatFieldName(header))];
    let csvContent = headers.join(',') + '\n';

    // Add rows
    extractionResults.forEach(doc => {
      const row = [doc.fileName];
      tableHeaders.forEach(header => {
        const value = getFieldValueForExport(doc, header);
        // Escape commas and quotes in CSV
        const escapedValue = `"${String(value).replace(/"/g, '""')}"`;
        row.push(escapedValue);
      });
      csvContent += row.join(',') + '\n';
    });

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `${projectName}_results.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (error) {
    console.error('Error exporting to Excel:', error);
    alert('Error exporting data. Please try again.');
  }
};

// Helper function for export (similar to getFieldValue but for export purposes)
 const getFieldValueForExport = (doc, fieldName) => {
  if (!doc.results || !doc.results[fieldName]) return "NULL";
  const fieldData = doc.results[fieldName];
  if (fieldData && typeof fieldData === 'object') {
    const v = fieldData.value;
    return v === null || v === undefined || v === "" ? "NULL" : v;
  }
  const v = String(fieldData);
  return v === "" ? "NULL" : v;
};

const Dashboard = ({ selectedProject, onMenuClick, selectedProjectId }) => {
  const [tabValue, setTabValue] = useState(0);
  const [docStatus, setDocStatus] = useState([]);
  const [extractionResults, setExtractionResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [tableHeaders, setTableHeaders] = useState([]);
  const theme = useTheme();
  const [editingCell, setEditingCell] = useState(null); // { rowKey, fieldName }
  const [editValue, setEditValue] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [toast, setToast] = useState({ open: false, message: "", severity: "success" });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const getProjectStatus = async () => {
    try {
      console.log("Fetching project details for project ID:", selectedProjectId);
      const result = await getProjectDetails(selectedProjectId);
      console.log("Fetched project details:", result);
      // Expecting shape { project_id, ..., documents: [ { doc_id, doc_name, status, ... } ] }
      setDocStatus(Array.isArray(result?.documents) ? result.documents : []);
    } catch (error) {
      console.error("Error fetching project details:", error);
    }
  };

  // Extract all fields from documents to create table headers (no filtering)
  const extractTableHeaders = (results) => {
    if (!results.length) return [];

    const allFields = new Set();
    
    results.forEach(doc => {
      if (doc.results && typeof doc.results === 'object') {
        Object.keys(doc.results).forEach((fieldName) => {
          allFields.add(fieldName);
        });
      }
    });

    // Convert to array and sort for consistent order
    return Array.from(allFields).sort();
  };

  const fetchExtractionResults = async () => {
    if (!selectedProjectId) return;
    
    try {
      setLoadingResults(true);
      console.log("Fetching extraction results for project:", selectedProjectId);
      // Fetch project-level results once
      const apiResponse = await getDocumentResults(selectedProjectId);
      console.log("API Response (project results):", apiResponse);

      const docsMap = apiResponse?.documents || {};

      // Consider only completed documents based on current docStatus
      const completedIds = new Set(
        (docStatus || [])
          .filter((d) => d.status === "completed")
          .map((d) => d.doc_id)
      );

      // Transform backend shape to table-friendly shape
      const resultsArray = Object.entries(docsMap)
        .filter(([docId]) => (completedIds.size ? completedIds.has(docId) : true))
        .map(([docId, docData]) => {
          const resultObj = {};
          (docData?.field_results || []).forEach((fr) => {
            resultObj[fr.field_name] = {
              value: fr.value,
              answer_html: fr.answer_html,
              explanation: fr.explanation,
              confidence: fr.confidence,
              source_pages: fr.source_pages,
              chunks: fr.chunks,
              status: fr.status,
              error_message: fr.error_message,
            };
          });
          return {
            id: docId,
            doc_id: docId,
            fileName: docData?.document_name || "",
            docName: docData?.document_name || "",
            results: resultObj,
          };
        });

      setExtractionResults(resultsArray);

      // Extract table headers from the transformed results
      const headers = extractTableHeaders(resultsArray);
      setTableHeaders(headers);
      
      console.log("Processed extraction results:", resultsArray);
      console.log("Generated table headers:", headers);
      
    } catch (error) {
      console.error("Error fetching extraction results:", error);
    } finally {
      setLoadingResults(false);
    }
  };

  const getStatusChip = (status) => {
    const statusConfig = {
      completed: {
        label: "Completed",
        color: "success",
        sx: {
          backgroundColor: theme.palette.success.light,
          color: theme.palette.success.dark,
          fontWeight: 600,
        },
      },
      processing: {
        label: "Processing",
        color: "warning",
        sx: {
          backgroundColor: theme.palette.warning.light,
          color: theme.palette.warning.dark,
          fontWeight: 600,
          animation: "pulse 2s infinite",
        },
      },
      pending: {
        label: "Pending",
        color: "default",
        sx: {
          backgroundColor: theme.palette.action.hover,
          color: theme.palette.text.secondary,
          fontWeight: 500,
        },
      },
    };

    const config = statusConfig[status] || statusConfig.pending;

    return (
      <Chip
        label={
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
            {status === "processing" && (
              <CircularProgress size={12} thickness={5} color="warning" />
            )}
            {status === "completed" && (
              <CheckCircleOutlineOutlinedIcon
                sx={{ fontSize: 14, color: theme.palette.success.main }}
              />
            )}
            {status === "pending" && (
              <InsertDriveFileOutlinedIcon
                sx={{ fontSize: 14, color: theme.palette.text.secondary }}
              />
            )}
            <span>{config.label}</span>
          </Box>
        }
        size="small"
        sx={{
          ...config.sx,
          borderRadius: "4px",
          "@keyframes pulse": {
            "0%": { opacity: 1 },
            "50%": { opacity: 0.7 },
            "100%": { opacity: 1 },
          },
        }}
      />
    );
  };
const handleExport = () => {
  exportToExcel(extractionResults, tableHeaders, selectedProject.name);
};
  const handleViewResults = () => {
    setTabValue(0);
    fetchExtractionResults();
  };

  // Ensure hooks are always called in the same order (move above any early returns)
  useEffect(() => {
    if (!selectedProjectId) return;
    // Clear previous project's data immediately to avoid stale display
    setDocStatus([]);
    setExtractionResults([]);
    setTableHeaders([]);

    getProjectStatus();
    const interval = setInterval(() => {
      getProjectStatus();
    }, 10000);

    return () => clearInterval(interval);
  }, [selectedProjectId]);

  // Fetch results when switching to results tab or when docStatus changes
  useEffect(() => {
    if (tabValue === 0 && selectedProjectId) {
      fetchExtractionResults();
    }
  }, [tabValue, selectedProjectId]);

  // Truncate long text for display
  const truncateText = (text, maxLength = 100) => {
    if (!text || text === "-") return "-";
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + "...";
  };

  // Get field value for a specific document
  const getFieldValue = (doc, fieldName) => {
    if (!doc.results || !doc.results[fieldName]) return "NULL";
    const fieldData = doc.results[fieldName];
    // Always show the value as-is (including "Information not found...")
    if (fieldData && typeof fieldData === 'object') {
      const v = fieldData.value;
      return v === null || v === undefined || v === "" ? "NULL" : v;
    }
    const v = String(fieldData);
    return v === "" ? "NULL" : v;
  };

  const getRowKey = (doc) => doc.doc_id || doc.results?.doc_id || doc.fileName || doc.id;

  const startEdit = (rowKey, fieldName, currentValue) => {
    setEditingCell({ rowKey, fieldName });
    setEditValue(currentValue === 'NULL' ? '' : String(currentValue));
  };

  const cancelEdit = () => {
    setEditingCell(null);
    setEditValue('');
  };

  const applyEdit = async () => {
    if (!editingCell) return;
    const { rowKey, fieldName } = editingCell;
    setSavingEdit(true);

    // optimistic local update
    setExtractionResults(prev => prev.map(d => {
      if (getRowKey(d) !== rowKey) return d;
      if (fieldName === 'doc_name') {
        return { ...d, fileName: editValue, docName: editValue };
      }
      const existing = d.results?.[fieldName];
      const nextValue = existing && typeof existing === 'object' ? { ...existing, value: editValue } : { value: editValue };
      return { ...d, results: { ...(d.results || {}), [fieldName]: nextValue } };
    }));

    try {
      const row = extractionResults.find(d => getRowKey(d) === rowKey) || {};
      const backendDocId = row.doc_id || row.results?.doc_id || rowKey;
      if (fieldName !== 'doc_name') {
        const existing = row.results?.[fieldName];
        const updates = {
          value: editValue,
          // Preserve source_pages if present; backend expects an array per provided curl
          source_pages: Array.isArray(existing?.source_pages) ? existing.source_pages : [],
        };
        await updateFieldResult(backendDocId, fieldName, updates);
      }
      setToast({ open: true, message: "Saved", severity: "success" });
      cancelEdit();
    } catch (e) {
      setToast({ open: true, message: "Failed to save. Reverting.", severity: "error" });
      fetchExtractionResults();
    } finally {
      setSavingEdit(false);
    }
  };

  // No counting of meaningful fields anymore; we display all fields returned by API

  if (!selectedProject) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "60vh",
          flexDirection: "column",
        }}
      >
        {/* <Typography variant="h6" color="text.secondary" gutterBottom>
          Current Project
        </Typography> */}
        <Typography variant="body1" color="text.secondary">
          Select a project from the sidebar to view details
        </Typography>
      </Box>
    );
  }

  

  return (
    <Box sx={{ width: "100%" }}>
      {/* Current Project Indicator */}
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <IconButton
          onClick={onMenuClick}
          sx={{
            mr: 1,
            "&:hover": {
              backgroundColor: "action.selected",
            },
          }}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect width="18" height="18" x="3" y="3" rx="2"></rect>
            <path d="M9 3v18"></path>
          </svg>
        </IconButton>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Project Header */}
      <Box sx={{ mb: 3 }}>
        <Typography
          // variant="h4"
          // component="h3"
          gutterBottom
          sx={{ fontSize: 24, fontWeight: 550, color: "text.primary" }}
        >
          {selectedProject.name}
        </Typography>
        <Typography variant="body1" color="text.secondary">
          View extraction results and processing status
        </Typography>
      </Box>

        <Box
          sx={{
            backgroundColor: (t) =>
              t.palette.mode === "dark"
                ? t.palette.action.hover
                : "#e5e7eb",
            display: "inline-flex",
            borderRadius: "8px",
            p: "3px",
            mb: 3,
            width: "27.99375rem"
          }}
        >
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            TabIndicatorProps={{ style: { display: "none" } }}
            
            sx={{
              minHeight: "unset",
              width: "100%",
              "& .MuiTabs-flexContainer": {
                display: "flex",
                gap: "4px",
                width: "100%",
                color: (t) =>
                  t.palette.mode === "dark"
                    ? t.palette.text.secondary
                    : "#111827",
              },
              "& .MuiTab-root": {
                textTransform: "none",
                fontWeight: 600,
                fontSize: "0.85rem", // Slightly smaller font
                // color: (t) => (t.palette.mode === "dark" ? t.palette.text.secondary : "#5f6368"),
                color: (t) => 
                  t.palette.mode === "dark" 
                    ? t.palette.text.secondary  
                    // : "#111827",
                    : "#4b5563",
                borderRadius: "4px",
                minHeight: "35px", // Reduced height
                padding: "5px 9px", // Reduced padding
                flex: 1,
                minWidth: "unset",
                // backgroundColor: "transparent",
                // transition: "all 0.2s ease",
              },
              "& .Mui-selected": {
                backgroundColor: (t) =>
                  t.palette.mode === "dark" ? t.palette.background.paper : "#fff",
                // color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#202124"),
                color: (t) => 
                  t.palette.mode === "dark" 
                    ? t.palette.text.primary 
                    : "#111827",
                boxShadow: (t) =>
                  t.palette.mode === "dark" ? "inset 0 0 0 1px rgba(255,255,255,0.08)" : "0 0 0 1px rgba(0,0,0,0.1)",
              },
              "& .MuiTab-root:hover": {
                backgroundColor: (t) =>
                  t.palette.mode === "dark" ? t.palette.action.selected : "#f1f3f4",
                color: (t) => 
                  t.palette.mode === "dark" 
                    ? t.palette.text.primary 
                    : "#111827",
              },
            }}
          >
            <Tab label="Results"  />
            <Tab label="Processing"   />
          </Tabs>
        </Box>



      {/* Results Tab */}
      <TabPanel value={tabValue} index={0} >
        <Box
        sx={{ p:3 ,height: '45vh', width: '100%',
          backgroundColor: (t) =>
            t.palette.mode === 'dark' ? t.palette.background.default : "#f5f6f7",
          borderRadius:2}}

         >
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 550 , fontSize:24,
             color: (theme) =>
              theme.palette.mode === "dark" ? "white" : "#282C34",
            "&.Mui-selected": {
              color: (theme) =>
                theme.palette.mode === "dark" ? "white" : "#282C34",
            },
          }}>
            Extraction Results
          </Typography>
          <Box sx={{ mb: 3 , display: 'flex', justifyContent: 'space-between', alignItems: 'center', }}>
            <Typography variant="body2" color="text.secondary">
              {loadingResults ? "Loading results..." : "Click any cell to edit extracted data"}
            </Typography>
            <Button
            variant="outlined"
            startIcon={<UploadOutlined />}
            onClick={handleExport}
            disabled={extractionResults.length === 0 || tableHeaders.length === 0}
            sx={{
              textTransform: 'none',
              fontWeight: 600,
              borderRadius: '6px',
              px: 2,
              py: 1
            }}
          >
            Export Results
          </Button>
          </Box>

          {loadingResults ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
              <CircularProgress />
            </Box>
          ) : extractionResults.length === 0 ? (
            <Box sx={{ textAlign: 'center', p: 3 }}>
              <Typography color="text.secondary">
                No extraction results available. Process some documents first.
              </Typography>
            </Box>
          ) : tableHeaders.length === 0 ? (
            <Box sx={{ textAlign: 'center', p: 3 }}>
              <Typography color="text.secondary" gutterBottom>
                No meaningful data extracted from the documents.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                The system processed {extractionResults.length} document(s) but didn't find extractable information matching the expected fields.
              </Typography>
            </Box>
          ) : (
            <TableContainer
              // component={Paper}
              // sx={{
              //   boxShadow: 1,
              //   overflowX: "auto",
              //   bgcolor: "background.paper",
              //   border: "1px solid",
              //   borderColor: "divider",
              //   borderRadius: 1,
              //   maxHeight: '60vh'
              // }}

              component={Paper}
              sx={{
                boxShadow: 1,
                overflowX: "auto",
                bgcolor: (t) => t.palette.background.paper,
                border: (t) => `1px solid ${t.palette.divider}`,
                borderRadius: 1,
                maxHeight: '60vh',
                // Slim horizontal scrollbar
                scrollbarWidth: 'thin',
                '&::-webkit-scrollbar': {
                  height: 6,
                },
                '&::-webkit-scrollbar-thumb': {
                  backgroundColor: (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.25)',
                  borderRadius: 8,
                },
                '&::-webkit-scrollbar-track': {
                  backgroundColor: 'transparent',
                },
              }}
            >
              <Table stickyHeader>
                <TableHead
                  sx={{
                    backgroundColor: (t) =>
                      t.palette.mode === "dark" ? t.palette.background.default : "#eef2f7",
                    "& .MuiTableCell-root": {
                      color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#111827"),
                      borderBottom: (t) => `1px solid ${t.palette.divider}`,
                      fontWeight: 700,
                      fontSize: "0.9rem",
                      py: 1.5,
                    },
                    // Ensure consistent header cell background
                    "& .MuiTableCell-head": {
                      backgroundColor: (t) =>
                        t.palette.mode === "dark" ? t.palette.background.default : "#eef2f7",
                    },
                  }}
                >
                  <TableRow>
                    <TableCell
                      sx={{ minWidth: 200 }}
                    >
                      File Name
                    </TableCell>
                    {tableHeaders.map((header) => (
                      <TableCell 
                        key={header} 
                        sx={{ minWidth: 180 }}
                      >
                        <Tooltip title={header} arrow>
                          <span>{formatFieldName(header)}</span>
                        </Tooltip>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody 

                >
                  {console.log(extractionResults , "extractionResults")}
                  {extractionResults.map((doc) => (
                    <TableRow
                      // key={doc.id}
                      
                      hover
                      sx={{
                        borderBottom: "1px solid",
                        borderColor: "divider",
                        "&:hover": {
                          backgroundColor: (t) =>
                            t.palette.mode === "dark"
                              ? alpha(t.palette.common.white, 0.04)
                              : alpha(t.palette.common.black, 0.04),
                        },
                      }}
                    >
                      <TableCell 
                        sx={{ 
                          minWidth: 200,
                          backgroundColor: (t) =>
                            t.palette.mode === "dark" ? t.palette.background.paper : "#f9fafb",
                        }}
                      >
                        {editingCell && editingCell.rowKey === getRowKey(doc)  ? (
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <TextField
                              size="small"
                              fullWidth
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              disabled={savingEdit}
                            />
                            <IconButton color="primary" onClick={applyEdit} disabled={savingEdit}>
                              <CheckIcon fontSize="small" />
                            </IconButton>
                            <IconButton onClick={cancelEdit} disabled={savingEdit}>
                              <CloseIcon fontSize="small" />
                            </IconButton>
                          </Box>
                        ) : (
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-start' }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <DescriptionIcon fontSize="small" color="action" />
                              <Tooltip title={doc.fileName} arrow>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontFamily: 'monospace',
                                    fontWeight: 500,
                                    display: 'block',
                                    maxWidth: '40ch',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {doc.fileName}
                                </Typography>
                              </Tooltip>
                            </Box>
                          </Box>
                        )}
                      </TableCell>
                      {tableHeaders.map((header) => (
                        <TableCell key={`${doc.id}-${header}`} sx={{
                          backgroundColor: (t) =>
                            t.palette.mode === "dark" ? t.palette.background.paper : "#f9fafb",
                        }}>
                          {editingCell && editingCell.rowKey === getRowKey(doc) && editingCell.fieldName === header ? (
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <TextField
                                size="small"
                                fullWidth
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                disabled={savingEdit}
                              />
                              <IconButton color="primary" onClick={applyEdit} disabled={savingEdit}>
                                <CheckIcon fontSize="small" />
                              </IconButton>
                              <IconButton onClick={cancelEdit} disabled={savingEdit}>
                                <CloseIcon fontSize="small" />
                              </IconButton>
                            </Box>
                          ) : (
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1 }}>
                              <Tooltip title={String(getFieldValue(doc, header))} arrow>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontStyle: getFieldValue(doc, header) === 'NULL' ? 'italic' : 'normal',
                                    color: getFieldValue(doc, header) === 'NULL' ? 'text.secondary' : 'text.primary',
                                    display: 'block',
                                    maxWidth: '30ch',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap'
                                  }}
                                  title={String(getFieldValue(doc, header))}
                                >
                                  {getFieldValue(doc, header)}
                                </Typography>
                              </Tooltip>
                              <IconButton size="small" onClick={() => startEdit(getRowKey(doc), header, getFieldValue(doc, header))}>
                                <EditOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Box>
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </TabPanel>
      {/* <Snackbar
        open={toast.open}
        autoHideDuration={2500}
        onClose={() => setToast({ ...toast, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setToast({ ...toast, open: false })} severity={toast.severity} sx={{ width: '100%' }}>
          {toast.message}
        </Alert>
      </Snackbar> */}

      {/* Processing Tab */}
      <TabPanel value={tabValue} index={1}>
        <Box 
                sx={{ p:3 ,height: '50vh', width: '100%',
                  // backgroundColor:"#f5f6f7"
                 backgroundColor: (t) =>
            t.palette.mode === 'dark' ? t.palette.background.default : "#f5f6f7"
                , borderRadius:2}}
>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 500, color: (theme) =>
        theme.palette.mode === "dark" ? "white" : "#282C34",
      "&.Mui-selected": {
        color: (theme) =>
          theme.palette.mode === "dark" ? "white" : "#282C34",
      }, }}>
            Processing Queue
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Real-time status of document processing
          </Typography>

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {docStatus.length === 0 ? (
              <Typography color="text.secondary" sx={{ textAlign: 'center', p: 3 }}>
                No documents in processing queue.
              </Typography>
            ) : (
              docStatus.map((item) => (
                <Card
                  key={item.doc_id || item.id}
                  sx={{
                    transition: "all 0.2s ease-in-out",
                    "&:hover": {
                      transform: "translateY(-2px)",
                    },
                  }}
                >
                  <CardContent sx={{ pb: 2 , backgroundColor: (t) =>
                          t.palette.mode === "dark"
                            ? t.palette.background.paper
                            : "#F5F9F7",}}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 2,
                        mb: 2,
                       
                      }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 40,
                          height: 40,
                          borderRadius: "50%",
                        }}
                      >
                        <InsertDriveFileOutlinedIcon />
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography
                          variant="body1"
                          sx={{
                            fontFamily: "monospace",
                            fontWeight: 600,
                            // color: theme.palette.text.primary,
                          }}
                        >
                          {item.doc_name}
                        </Typography>
                      </Box>
                      {getStatusChip(item.status)}
                    </Box>

                    {item.status === "processing" && (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                        <LinearProgress
                          variant="determinate"
                          value={item.progress || 0}
                          sx={{
                            flex: 1,
                            height: 8,
                            borderRadius: 4,
                            "& .MuiLinearProgress-bar": {
                              borderRadius: 4,
                            },
                          }}
                        />
                        {/* <Typography
                          variant="body2"
                          sx={{
                            color: theme.palette.text.secondary,
                            fontWeight: 600,
                            minWidth: 40,
                          }}
                        >
                          {item.progress || 0}%
                        </Typography> */}
                      </Box>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </Box>
        </Box>
      </TabPanel>

      {tabValue === 1 && (
        <Box
          sx={{
            display: "flex",
            justifyContent: "flex-end",
            mt: 3,
            mb: 1,
          }}
        >
          <Button
            onClick={handleViewResults}
            startIcon={<VisibilityOutlinedIcon />}
            sx={{
              textTransform: "none",
              fontWeight: 600,
              borderRadius: "8px",
              px: 3,
              py: 1,
              border: "1px solid",
              borderColor: theme.palette.divider,
              color: theme.palette.text.primary,
              "&:hover": {
                backgroundColor: theme.palette.action.hover,
              },
            }}
          >
            View Results
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default Dashboard;