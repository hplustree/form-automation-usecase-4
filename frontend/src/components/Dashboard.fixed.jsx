import React, { useEffect, useMemo, useState } from "react";
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
  Alert,
} from "@mui/material";
import { Description as DescriptionIcon } from "@mui/icons-material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import DownloadIcon from '@mui/icons-material/Download';
import {
  get_document_status,
  getDocumentResults,
  updateDocumentResult,
  exportToExcel,
  getFieldValueForExport
} from "../api/api";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box>{children}</Box>}
    </div>
  );
}

const formatFieldName = (fieldName) =>
  String(fieldName)
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");

const Dashboard = ({ selectedProject, onMenuClick, selectedProjectId }) => {
  const theme = useTheme();
  const [tabValue, setTabValue] = useState(0);
  const [docStatus, setDocStatus] = useState([]);
  const [extractionResults, setExtractionResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [tableHeaders, setTableHeaders] = useState([]);
  const [editingCell, setEditingCell] = useState(null); // { rowKey, fieldName }
  const [editValue, setEditValue] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [toast, setToast] = useState({ open: false, message: "", severity: "success" });

  const handleTabChange = (_e, v) => setTabValue(v);

  const getStatusChip = (status) => {
    const map = {
      queued: { label: "Queued", color: "default" },
      processing: { label: "Processing", color: "primary" },
      completed: { label: "Completed", color: "success" },
      failed: { label: "Failed", color: "error" },
    };
    const s = map[status] || { label: status || "Unknown", color: "default" };
    return <Chip size="small" label={s.label} color={s.color} variant="outlined" />;
  };

  const getFieldValue = (doc, fieldName) => {
    if (!doc || !fieldName) return "NULL";
    const data = doc.results?.[fieldName];
    if (data && typeof data === "object") {
      const v = data.value;
      return v === null || v === undefined || v === "" ? "NULL" : v;
    }
    if (data === null || data === undefined || data === "") return "NULL";
    return String(data);
  };

  const getRowKey = (doc) => doc.doc_id || doc.results?.doc_id || doc.fileName || doc.id;

  const startEdit = (rowKey, fieldName, currentValue) => {
    setEditingCell({ rowKey, fieldName });
    setEditValue(currentValue === "NULL" ? "" : String(currentValue));
  };

  const cancelEdit = () => {
    setEditingCell(null);
    setEditValue("");
  };

  const applyEdit = async () => {
    if (!editingCell) return;
    const { rowKey, fieldName } = editingCell;
    setSavingEdit(true);
    // Optimistic UI update
    setExtractionResults((prev) =>
      prev.map((d) => {
        if (getRowKey(d) !== rowKey) return d;
        if (fieldName === "doc_name" || fieldName === "fileName") {
          return { ...d, fileName: editValue, doc_name: editValue };
        }
        const existing = d.results?.[fieldName];
        const nextValue =
          existing && typeof existing === "object"
            ? { ...existing, value: editValue }
            : { value: editValue };
        return { ...d, results: { ...(d.results || {}), [fieldName]: nextValue } };
      })
    );

    try {
      const row = extractionResults.find((d) => getRowKey(d) === rowKey) || {};
      const backendDocId = row.doc_id || row.results?.doc_id || rowKey;
      await updateDocumentResult(selectedProjectId, backendDocId, fieldName, editValue);
      setToast({ open: true, message: "Saved", severity: "success" });
      cancelEdit();
    } catch (_e) {
      setToast({ open: true, message: "Failed to save. Reverting.", severity: "error" });
      fetchExtractionResults();
    } finally {
      setSavingEdit(false);
    }
  };

  const exportResultsToCSV = () => {
    if (!extractionResults || extractionResults.length === 0) return;
    const headers = ["File Name", ...tableHeaders];
    const rows = extractionResults.map((doc) => [
      doc.fileName || doc.doc_name || "",
      ...tableHeaders.map((h) => {
        const v = getFieldValue(doc, h);
        return v === "NULL" ? "" : String(v);
      }),
    ]);

    const escapeCsv = (value) => {
      const str = String(value ?? "");
      const escaped = str.replace(/"/g, '""');
      return `"${escaped}"`;
    };

    const csv = [
      headers.map(escapeCsv).join(","),
      ...rows.map((r) => r.map(escapeCsv).join(",")),
    ].join("\r\n");

    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "extraction_results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const getProjectStatus = async () => {
    try {
      const res = await get_document_status(selectedProjectId);
      // API returns response.data already; treat res as the payload
      setDocStatus(Array.isArray(res) ? res : []);
    } catch (_e) {
      setDocStatus([]);
    }
  };

  const fetchExtractionResults = async () => {
    setLoadingResults(true);
    try {
      const res = await getDocumentResults(selectedProjectId);
      // API returns response.data already; treat res as the payload
      const list = Array.isArray(res) ? res : [];
      // Normalize items to ensure fileName is populated for rendering keys/cells
      const normalized = list.map((doc) => ({
        ...doc,
        fileName: doc?.fileName || doc?.doc_name || doc?.docName || "",
      }));
      setExtractionResults(normalized);
      const headersSet = new Set();
      normalized.forEach((doc) => {
        if (doc?.results && typeof doc.results === "object") {
          Object.keys(doc.results).forEach((k) => headersSet.add(k));
        }
      });
      const headersArr = Array.from(headersSet);
      setTableHeaders(headersArr);
    } catch (_e) {
      setExtractionResults([]);
      setTableHeaders([]);
    } finally {
      setLoadingResults(false);
    }
  };

//   const handleViewResults = () => setTabValue(0);
//   console.log(selectedProjectId , "selected proejct id ")
//   useEffect(() => {
//     if (!selectedProjectId) return;
//     setDocStatus([]);
//     setExtractionResults([]);
//     setTableHeaders([]);
//     getProjectStatus();
//     // If user is on Results tab when switching projects, fetch results immediately
//     // if (tabValue === 0) {
//       fetchExtractionResults();
//     // }
//     const interval = setInterval(getProjectStatus, 10000);
//     return () => clearInterval(interval);
//   }, [selectedProjectId]);

//   useEffect(() => {
//     // if (tabValue === 0 && selectedProjectId)
//     if (tabValue === 0 && selectedProjectId){
        
//          fetchExtractionResults();
//     }

//   }, [tabValue, selectedProjectId]);


    const handleExport = () => {
    exportToExcel(extractionResults, tableHeaders, selectedProject.name);
    };

  const handleViewResults = () => setTabValue(0);

  useEffect(() => {
    if (!selectedProjectId) return;
    setDocStatus([]);
    setExtractionResults([]);
    setTableHeaders([]);
    getProjectStatus();
    fetchExtractionResults();
    const interval = setInterval(getProjectStatus, 10000);
    return () => clearInterval(interval);
  }, [selectedProjectId]);

  useEffect(() => {
    if (tabValue === 0 && selectedProjectId) {
      fetchExtractionResults();
    }
  }, [tabValue, selectedProjectId]);

  if (!selectedProject) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "60vh", flexDirection: "column" }}>
        <Typography variant="h6" color="text.secondary" gutterBottom>
          Current Project
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Select a project from the sidebar to view details
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ width: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <IconButton
          onClick={onMenuClick}
          sx={{ mr: 1, "&:hover": { backgroundColor: "action.selected" } }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"></rect>
            <path d="M9 3v18"></path>
          </svg>
        </IconButton>
      </Box>

      <Divider sx={{ mb: 2 }} />

      <Box sx={{ mb: 3 }}>
        <Typography gutterBottom sx={{ fontSize: 24, fontWeight: 550, color: "text.primary" }}>
          {selectedProject.name}
        </Typography>
        <Typography variant="body1" color="text.secondary">
          View extraction results and processing status
        </Typography>
      </Box>

      <Box
        sx={{
          backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.action.hover : "#e5e7eb"),
          display: "inline-flex",
          borderRadius: "8px",
          p: "3px",
          mb: 3,
          width: "27.99375rem",
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
              color: (t) => (t.palette.mode === "dark" ? t.palette.text.secondary : "#4b5563"),
            },
            "& .MuiTab-root": {
              textTransform: "none",
              fontWeight: 600,
              fontSize: "0.85rem",
              color: (t) => (t.palette.mode === "dark" ? t.palette.text.secondary : "#4b5563"),
              borderRadius: "4px",
              minHeight: "35px",
              padding: "5px 9px",
              flex: 1,
              minWidth: "unset",
            },
            "& .Mui-selected": {
              backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.paper : "#fff"),
              color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#111827"),
              boxShadow: (t) => (t.palette.mode === "dark" ? "inset 0 0 0 1px rgba(255,255,255,0.08)" : "0 0 0 1px rgba(0,0,0,0.1)"),
            },
            "& .MuiTab-root:hover": {
              backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.action.selected : "#f1f3f4"),
              color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#111827"),
            },
          }}
        >
          <Tab label="Results" />
          <Tab label="Processing" />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        <Box sx={{ p: 3, height: "45vh", width: "100%", backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.default : "#f5f6f7"), borderRadius: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 550, fontSize: 24, color: (t) => (t.palette.mode === "dark" ? "white" : "#282C34") }}>
              Extraction Results
            </Typography>
            <Button onClick={exportResultsToCSV} size="small" variant="outlined" sx={{ textTransform: "none", fontWeight: 600 }} disabled={loadingResults || extractionResults.length === 0}>
              Export
            </Button>
          </Box>

          {/* <Box sx={{ mb: 3 }}>
            <Typography variant="body2" color="text.secondary">
              {loadingResults ? "Loading results..." : "Click any cell to edit extracted data"}
            </Typography>
          </Box> */}


          {/* Export Button and Instructions Row */}
<Box sx={{ 
  display: 'flex', 
  justifyContent: 'space-between', 
  alignItems: 'center', 
  mb: 3 
}}>
  <Typography variant="body2" color="text.secondary">
    {loadingResults ? "Loading results..." : "Click any cell to edit extracted data"}
  </Typography>
  
  <Button
    variant="outlined"
    startIcon={<DownloadIcon />}
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
          {console.log(extractionResults , "extractionResults")}
          {loadingResults ? (
            <Box sx={{ display: "flex", justifyContent: "center", p: 3 }}>
              <CircularProgress />
            </Box>
          ) : extractionResults.length === 0 ? (
            <Box sx={{ textAlign: "center", p: 3 }}>
              <Typography color="text.secondary">No extraction results available. Process some documents first.</Typography>
            </Box>
          ) : tableHeaders.length === 0 ? (
            <Box sx={{ textAlign: "center", p: 3 }}>
              <Typography color="text.secondary" gutterBottom>
                No meaningful data extracted from the documents.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                The system processed {extractionResults.length} document(s) but didn't find extractable information matching the expected fields.
              </Typography>
            </Box>
          ) : (
            <TableContainer
              component={Paper}
              sx={{
                boxShadow: 1,
                overflowX: "auto",
                bgcolor: (t) => t.palette.background.paper,
                border: (t) => `1px solid ${t.palette.divider}`,
                borderRadius: 1,
                maxHeight: "60vh",
                scrollbarWidth: "thin",
                "&::-webkit-scrollbar": { height: 6 },
                "&::-webkit-scrollbar-thumb": {
                  backgroundColor: (t) => (t.palette.mode === "dark" ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.25)"),
                  borderRadius: 8,
                },
                "&::-webkit-scrollbar-track": { backgroundColor: "transparent" },
              }}
            >
              <Table stickyHeader>
                <TableHead
                  sx={{
                    backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.default : "#eef2f7"),
                    "& .MuiTableCell-root": {
                      color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#111827"),
                      borderBottom: (t) => `1px solid ${t.palette.divider}`,
                      fontWeight: 700,
                      fontSize: "0.9rem",
                      py: 1.5,
                    },
                    "& .MuiTableCell-head": {
                      backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.default : "#eef2f7"),
                    },
                  }}
                >
                  <TableRow>
                    <TableCell sx={{ minWidth: 200 }}>File Name</TableCell>
                    {tableHeaders.map((header) => (
                      <TableCell key={header} sx={{ minWidth: 180 }}>
                        <Tooltip title={header} arrow>
                          <span>{formatFieldName(header)}</span>
                        </Tooltip>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {extractionResults.map((doc) => (
                    <TableRow
                      key={getRowKey(doc)}
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
                      <TableCell sx={{ minWidth: 200, backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.paper : "#f9fafb") }}>
                        {editingCell && editingCell.rowKey === getRowKey(doc) && editingCell.fieldName === "doc_name" ? (
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <TextField size="small" fullWidth value={editValue} onChange={(e) => setEditValue(e.target.value)} disabled={savingEdit} />
                            <IconButton color="primary" onClick={applyEdit} disabled={savingEdit}>
                              <CheckIcon fontSize="small" />
                            </IconButton>
                            <IconButton onClick={cancelEdit} disabled={savingEdit}>
                              <CloseIcon fontSize="small" />
                            </IconButton>
                          </Box>
                        ) : (
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1, justifyContent: "space-between" }}>
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <DescriptionIcon fontSize="small" color="action" />
                              <Tooltip title={doc.fileName} arrow>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontFamily: "monospace",
                                    fontWeight: 500,
                                    display: "block",
                                    maxWidth: "40ch",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                  }}
                                >
                                  {doc.fileName}
                                </Typography>
                              </Tooltip>
                            </Box>
                            <IconButton size="small" onClick={() => startEdit(getRowKey(doc), "doc_name", doc.fileName)}>
                              <EditOutlinedIcon fontSize="small" />
                            </IconButton>
                          </Box>
                        )}
                      </TableCell>

                      {tableHeaders.map((header) => (
                        <TableCell key={`${getRowKey(doc)}-${header}`} sx={{ backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.paper : "#f9fafb") }}>
                          {editingCell && editingCell.rowKey === getRowKey(doc) && editingCell.fieldName === header ? (
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <TextField size="small" fullWidth value={editValue} onChange={(e) => setEditValue(e.target.value)} disabled={savingEdit} />
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
                                    fontStyle: getFieldValue(doc, header) === "NULL" ? "italic" : "normal",
                                    color: getFieldValue(doc, header) === "NULL" ? "text.secondary" : "text.primary",
                                    display: "block",
                                    maxWidth: "30ch",
                                    // overflow: "hidden",
                                    // textOverflow: "ellipsis",
                                    // whiteSpace: "nowrap",
                                    // textOverflow: "break-word",
                                    whiteSpace: "normal",     
                                    wordBreak: "break-word"
                                    
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

      <Snackbar
        open={toast.open}
        autoHideDuration={2500}
        onClose={() => setToast({ ...toast, open: false })}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={() => setToast({ ...toast, open: false })} severity={toast.severity} sx={{ width: "100%" }}>
          {toast.message}
        </Alert>
      </Snackbar>

      <TabPanel value={tabValue} index={1}>
        <Box sx={{ p: 3, height: "50vh", width: "100%", backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.default : "#f5f6f7"), borderRadius: 2 }}>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 500, color: (t) => (t.palette.mode === "dark" ? "white" : "#282C34") }}>
            Processing Queue
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Real-time status of document processing
          </Typography>

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {docStatus.length === 0 ? (
              <Typography color="text.secondary" sx={{ textAlign: "center", p: 3 }}>
                No documents in processing queue.
              </Typography>
            ) : (
              docStatus.map((item) => (
                <Card key={item.doc_id || item.id} sx={{ transition: "all 0.2s ease-in-out", "&:hover": { transform: "translateY(-2px)" } }}>
                  <CardContent sx={{ pb: 2, backgroundColor: (t) => (t.palette.mode === "dark" ? t.palette.background.paper : "#F5F9F7") }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", width: 40, height: 40, borderRadius: "50%" }}>
                        <InsertDriveFileOutlinedIcon />
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body1" sx={{ fontFamily: "monospace", fontWeight: 600 }}>
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
                          sx={{ flex: 1, height: 8, borderRadius: 4, "& .MuiLinearProgress-bar": { borderRadius: 4 } }}
                        />
                        <Typography variant="body2" sx={{ color: theme.palette.text.secondary, fontWeight: 600, minWidth: 40 }}>
                          {item.progress || 0}%
                        </Typography>
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
        <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 3, mb: 1 }}>
          <Button
            onClick={handleViewResults}
            startIcon={<VisibilityOutlinedIcon />}
            sx={{ textTransform: "none", fontWeight: 600, borderRadius: "8px", px: 3, py: 1, border: "1px solid", borderColor: theme.palette.divider, color: theme.palette.text.primary, "&:hover": { backgroundColor: theme.palette.action.hover } }}
          >
            View Results
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default Dashboard;
