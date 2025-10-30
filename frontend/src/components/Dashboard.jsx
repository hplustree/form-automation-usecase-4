import React, { useEffect, useState } from "react";
import { alpha } from "@mui/material/styles";
import {
  Box,
  Typography,
  Divider,
  Card,
  CardContent,
  Tabs,
  Tab,
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
  TextField,
  Tooltip,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
  Snackbar,
  Checkbox,
  FormGroup,
  FormControlLabel
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
import AutorenewIcon from '@mui/icons-material/Autorenew';
import { get_document_status, getDocumentResults, getProjectDetails, updateFieldResult, regenerateDocument } from "../api/api";
import AddDocumentModal from "./AddDocumentModal";
import AddIcon from '@mui/icons-material/Add';

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
    // Create CSV content with fields in first column and document names as headers
    const docNames = extractionResults.map(doc => doc.fileName);
    const headers = ['File Name', ...docNames];
    let csvContent = headers.join(',') + '\n';

    // Add rows for each field
    tableHeaders.forEach(header => {
      const row = [formatFieldName(header)];
      extractionResults.forEach(doc => {
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

 const exportToWord = (extractionResults, tableHeaders, projectName) => {
  if (!extractionResults.length || !tableHeaders.length) return;

  try {
    const docNames = extractionResults.map(doc => doc.fileName);
    const headers = ['File Name', ...docNames];
    
    // Build HTML table
    const thead = `<tr>${headers.map(h => `<th style="border:1px solid #ccc;padding:6px;text-align:left;background-color:#f5f5f5;">${h}</th>`).join('')}</tr>`;
    
    // Add rows for each field
    const tbody = tableHeaders.map(header => {
      const fieldName = formatFieldName(header);
      const values = extractionResults.map(doc => {
        const value = String(getFieldValueForExport(doc, header));
        return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      });
      return `<tr>
        <td style="border:1px solid #ccc;padding:6px;font-weight:500;background-color:#f9f9f9;">${fieldName}</td>
        ${values.map(v => `<td style="border:1px solid #ccc;padding:6px;vertical-align:top;white-space:pre-wrap;">${v}</td>`).join('')}
      </tr>`;
    }).join('');
    
    const html = `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>${projectName} Results</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; }
          h2 { color: #333; }
          table { border-collapse: collapse; width: 100%; margin-top: 15px; }
          th { background-color: #f5f5f5; font-weight: bold; }
          td, th { border: 1px solid #ddd; padding: 8px; }
          tr:nth-child(even) { background-color: #f9f9f9; }
        </style>
      </head>
      <body>
        <h2>${projectName} - Extraction Results</h2>
        <table>
          ${thead}
          ${tbody}
        </table>
      </body>
      </html>
    `;

    const blob = new Blob([html], { type: 'application/msword;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `${projectName}_results.doc`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (error) {
    console.error('Error exporting to Word:', error);
    alert('Error exporting data. Please try again.');
  }
 };

const Dashboard = ({ selectedProject, onMenuClick, selectedProjectId }) => {
  const [tabValue, setTabValue] = useState(0);
  const [docStatus, setDocStatus] = useState([]);
  const [statusByDoc, setStatusByDoc] = useState({}); // { doc_id: 'pending'|'processing'|'completed' }
  const [extractionResults, setExtractionResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [tableHeaders, setTableHeaders] = useState([]);
  const theme = useTheme();
  const [editingCell, setEditingCell] = useState(null); // { rowKey, fieldName }
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState({ success: false, message: '' });
  const [toast, setToast] = useState({ open: false, message: "", severity: "success" });
  const [isEditing, setIsEditing] = useState(false);
  const [editedValues, setEditedValues] = useState({}); // { rowKey: { fieldName: value } }
  const [savingEdit, setSavingEdit] = useState(false);
  const [explanationDialog, setExplanationDialog] = useState({
    open: false,
    title: '',
    content: ''
  });
  const [addDocumentOpen, setAddDocumentOpen] = useState(false);
  const [regenerating, setRegenerating] = useState({});
  const [viewFieldsOpen, setViewFieldsOpen] = useState(false);
  const [tempSelectedFields, setTempSelectedFields] = useState([]);
  const [exportFieldsOpen, setExportFieldsOpen] = useState(false);
  const [tempExportFields, setTempExportFields] = useState([]);
  const [exportMode, setExportMode] = useState(null); // 'excel' | 'word'

  // Handler for adding documents
  const handleAddDocument = (files) => {
    setToast({
      open: true,
      message: `Successfully added ${files.length} document(s)`,
      severity: "success",
    });
    // Refresh the document list after adding
    getProjectStatus();
  };

  const handleRegenerate = async (doc) => {
    const docId = doc.doc_id || doc.id;
    if (!selectedProjectId || !docId) return;
    setRegenerating(prev => ({ ...prev, [docId]: true }));

    // Read selected field names for this project
    let fieldNames = [];
    try {
      const fieldsMap = JSON.parse(sessionStorage.getItem('project_fields_map')) || {};
      if (Array.isArray(fieldsMap[selectedProjectId])) fieldNames = fieldsMap[selectedProjectId];
    } catch (e) {
      console.warn('Failed to load project fields from sessionStorage', e);
    }

    // Optimistically set status to processing
    setStatusByDoc(prev => ({ ...prev, [docId]: 'processing' }));
    setDocStatus(prev => prev.map(d => (d.doc_id === docId || d.id === docId) ? { ...d, status: 'processing', progress: 0 } : d));

    try {
      await regenerateDocument(selectedProjectId, docId, fieldNames);
      setToast({ open: true, message: `Regeneration requested for ${doc.doc_name || doc.fileName || 'document'}`, severity: 'success' });
      // Let polling update actual status/progress
    } catch (e) {
      console.error('Failed to request regeneration', e);
      setToast({ open: true, message: 'Failed to request regeneration', severity: 'error' });
    } finally {
      setRegenerating(prev => ({ ...prev, [docId]: false }));
      // Trigger an immediate refresh
      // getProjectStatus();
    }
  };

  const handleOpenExplanation = (title, content) => {
    setExplanationDialog({
      open: true,
      title,
      content: content || 'No explanation available.'
    });
  };

  const handleCloseExplanation = () => {
    setExplanationDialog(prev => ({ ...prev, open: false }));
  };

  const buildRedirectUrl = (page) => {
    const base = import.meta.env.VITE_RESULTS_PAGE_BASE_URL || "";
    if (!base) return "";
    const pageNumber = Number(page);
    return `${base}${pageNumber}`;
  };

  const handlePageClick = (page) => {
    const url = buildRedirectUrl(page);
    if (url) {
      window.location.assign(url);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const getProjectStatus = async () => {
    try {
      const result = await getProjectDetails(selectedProjectId);
      // Expecting shape { project_id, ..., documents: [ { doc_id, doc_name, status, ... } ] }
      const docs = Array.isArray(result?.documents) ? result.documents : [];

      // Normalize and prevent status downgrade
      const rank = { pending: 0, processing: 1, completed: 2 };
      const merged = docs.map((d) => {
        const id = d.doc_id || d.id;
        const curr = normalizeStatus(d.status);
        const prev = statusByDoc[id] ? normalizeStatus(statusByDoc[id]) : undefined;
        const chosen = prev !== undefined && rank[prev] > rank[curr] ? prev : curr;
        return { ...d, status: chosen };
      });

      setDocStatus(merged);
      // Update local cache
      setStatusByDoc((prevMap) => {
        const next = { ...prevMap };
        merged.forEach((d) => {
          const id = d.doc_id || d.id;
          next[id] = d.status;
        });
        return next;
      });
    } catch (error) {
      console.error("Error fetching project details:", error);
    }
  };

  // Extract all fields from documents to create table headers (fallback only)
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

  // Read selected headers from sessionStorage (by projectId > name > last created name)
  const getSelectedHeaders = () => {
    try {
      let headers = [];
      if (selectedProjectId) {
        const fieldsMap = JSON.parse(sessionStorage.getItem('project_fields_map')) || {};
        headers = Array.isArray(fieldsMap[selectedProjectId]) ? fieldsMap[selectedProjectId] : [];
      }
      if ((!headers || headers.length === 0) && selectedProject?.name) {
        const fieldsByName = JSON.parse(sessionStorage.getItem('project_fields_map_by_name')) || {};
        const nameHeaders = Array.isArray(fieldsByName[selectedProject.name]) ? fieldsByName[selectedProject.name] : [];
        if (nameHeaders.length) headers = nameHeaders;
      }
      if ((!headers || headers.length === 0)) {
        const lastCreated = sessionStorage.getItem('last_created_project_name');
        if (lastCreated) {
          const fieldsByName = JSON.parse(sessionStorage.getItem('project_fields_map_by_name')) || {};
          const lastHeaders = Array.isArray(fieldsByName[lastCreated]) ? fieldsByName[lastCreated] : [];
          if (lastHeaders.length) headers = lastHeaders;
        }
      }
      return Array.isArray(headers) ? headers : [];
    } catch (e) {
      console.warn('Failed to load project fields from sessionStorage', e);
      return [];
    }
  };

  const fetchExtractionResults = async () => {
    if (!selectedProjectId) return;
    
    try {
      setLoadingResults(true);
      const apiResponse = await getDocumentResults(selectedProjectId);
      const docsMap = apiResponse?.documents || {};

      // Transform backend shape to table-friendly shape (include all available results; filtering is via headers)
      const resultsArray = Object.entries(docsMap)
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
      // If backend has no results yet, preserve any pre-seeded UI (do not overwrite)
      if (resultsArray.length > 0) {
        setExtractionResults(resultsArray);
        const preferred = getSelectedHeaders();
        if (preferred.length) {
          setTableHeaders(preferred);
        } else {
          const headersFromBackend = extractTableHeaders(resultsArray);
          if (headersFromBackend.length) setTableHeaders(headersFromBackend);
        }
      } else {
        console.log('No backend results yet; preserving pre-seeded table.');
      }
      
    } catch (error) {
      console.error("Error fetching extraction results:", error);
    } finally {
      setLoadingResults(false);
    }
  };

  // Load expected headers from sessionStorage. Prefer by projectId; fallback to project name pre-seed; then last created name
  useEffect(() => {
    const headers = getSelectedHeaders();
    if (headers && headers.length) setTableHeaders(headers);
  }, [selectedProjectId, selectedProject?.name]);

  const normalizeStatus = (raw) => {
    if (!raw) return 'pending';
    const s = String(raw).toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
    if (["completed","complete","processed","done","success","succeeded"].includes(s)) return "completed";
    if (["processing","in_progress","running","queued","inprogress" , "chunks_ready"].includes(s)) return "processing";
    if (["pending","created","waiting","queued_pending"].includes(s)) return "pending";
    return 'pending';
  };

  const getStatusChip = (statusRaw) => {
    const status = normalizeStatus(statusRaw);
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

  const handleExportWord = () => {
    exportToWord(extractionResults, tableHeaders, selectedProject.name);
  };

  // Export selection dialog handlers
  const openExportDialog = (mode) => {
    const fields = getAllAvailableFields();
    setTempExportFields(tableHeaders && tableHeaders.length ? [...tableHeaders] : [...fields]);
    setExportMode(mode);
    setExportFieldsOpen(true);
  };

  const toggleTempExportField = (field) => {
    setTempExportFields((prev) => {
      const set = new Set(prev);
      if (set.has(field)) set.delete(field);
      else set.add(field);
      return Array.from(set);
    });
  };

  const applyExport = () => {
    const fields = Array.isArray(tempExportFields) ? tempExportFields : [];
    if (!fields.length) return;
    if (exportMode === 'excel') {
      exportToExcel(extractionResults, fields, selectedProject.name);
    } else if (exportMode === 'word') {
      exportToWord(extractionResults, fields, selectedProject.name);
    }
    setExportFieldsOpen(false);
    setExportMode(null);
  };

  const handleViewResults = () => {
    setTabValue(0);
    fetchExtractionResults();
  };

  // Compute dynamic label for Processing tab
  const isAllCompleted = docStatus && docStatus.length > 0 && docStatus.every((d) => normalizeStatus(d.status) === 'completed');
  const processingTabLabel = isAllCompleted ? 'Completed' : 'Processing';

  const startGlobalEdit = () => {
    setIsEditing(true);
    setEditedValues({});
  };

  const cancelGlobalEdit = () => {
    setIsEditing(false);
    setEditedValues({});
  };

  const handleFieldChange = (rowKey, fieldName, value) => {
    setEditedValues((prev) => ({
      ...prev,
      [rowKey]: { ...(prev[rowKey] || {}), [fieldName]: value },
    }));
  };

  const saveAllEdits = async () => {
    if (!isEditing) return;
    try {
      setSavingEdit(true);
      const updates = [];
      // Build updates only for changed values
      Object.entries(editedValues).forEach(([rowKey, fieldsMap]) => {
        const row = extractionResults.find((d) => getRowKey(d) === rowKey);
        if (!row) return;
        const backendDocId = row.doc_id || row.results?.doc_id || rowKey;
        Object.entries(fieldsMap).forEach(([fieldName, newVal]) => {
          if (fieldName === 'doc_name') return; // never update document name
          const original = getFieldValue(row, fieldName);
          if (String(original) !== String(newVal)) {
            const existing = row.results?.[fieldName];
            updates.push({
              backendDocId,
              fieldName,
              newVal,
              source_pages: Array.isArray(existing?.source_pages) ? existing.source_pages : [],
            });
          }
        });
      });

      if (updates.length === 0) {
        setToast({ open: true, message: 'No changes to save', severity: 'info' });
        setIsEditing(false);
        setEditedValues({});
        return;
      }

      await Promise.all(
        updates.map((u) =>
          updateFieldResult(u.backendDocId, u.fieldName, { value: u.newVal, source_pages: u.source_pages })
        )
      );

      // Optimistically update local state
      setExtractionResults((prev) =>
        prev.map((d) => {
          const rowKey = getRowKey(d);
          const fieldsMap = editedValues[rowKey];
          if (!fieldsMap) return d;
          const nextResults = { ...(d.results || {}) };
          Object.entries(fieldsMap).forEach(([fieldName, val]) => {
            if (fieldName === 'doc_name') return;
            const existing = nextResults[fieldName];
            nextResults[fieldName] = existing && typeof existing === 'object' ? { ...existing, value: val } : { value: val };
          });
          return { ...d, results: nextResults };
        })
      );

      setToast({ open: true, message: 'All changes saved', severity: 'success' });
      setIsEditing(false);
      setEditedValues({});
    } catch (e) {
      console.error('Failed to save edits', e);
      setToast({ open: true, message: 'Failed to save changes', severity: 'error' });
    } finally {
      setSavingEdit(false);
    }
  };

  // Ensure hooks are always called in the same order (move above any early returns)
  useEffect(() => {
    const lastCreated = sessionStorage.getItem('last_created_project_name');
    if (!selectedProjectId && !selectedProject?.name && !lastCreated) return;
    // Clear previous project's data immediately to avoid stale display
    setDocStatus([]);
    setExtractionResults([]);
    setTableHeaders([]);

    if (selectedProjectId) {
      getProjectStatus();
    }

    // Preload pending seed (documents and placeholder field values) for immediate Results rendering
    let seeded = false;
    try {
      if (selectedProjectId) {
        const seedsMap = JSON.parse(sessionStorage.getItem('pending_results_seed')) || {};
        const seed = Array.isArray(seedsMap[selectedProjectId]) ? seedsMap[selectedProjectId] : [];
        if (seed.length) {
          setExtractionResults(seed);
          const preferred = getSelectedHeaders();
          if (preferred.length) setTableHeaders(preferred);
          else {
            const headersFromSeed = extractTableHeaders(seed);
            if (headersFromSeed.length) setTableHeaders(headersFromSeed);
          }
          seeded = true;
        }
      }
      if (!seeded && selectedProject?.name) {
        const seedsMapByName = JSON.parse(sessionStorage.getItem('pending_results_seed_by_name')) || {};
        const nameSeed = Array.isArray(seedsMapByName[selectedProject.name]) ? seedsMapByName[selectedProject.name] : [];
        if (nameSeed.length) {
          setExtractionResults(nameSeed);
          const preferred = getSelectedHeaders();
          if (preferred.length) setTableHeaders(preferred);
          else {
            const headersFromNameSeed = extractTableHeaders(nameSeed);
            if (headersFromNameSeed.length) setTableHeaders(headersFromNameSeed);
          }
          seeded = true;
        }
      }
      if (!seeded && lastCreated) {
        const seedsMapByName = JSON.parse(sessionStorage.getItem('pending_results_seed_by_name')) || {};
        const lastSeed = Array.isArray(seedsMapByName[lastCreated]) ? seedsMapByName[lastCreated] : [];
        if (lastSeed.length) {
          setExtractionResults(lastSeed);
          const preferred = getSelectedHeaders();
          if (preferred.length) setTableHeaders(preferred);
          else {
            const headersFromLastSeed = extractTableHeaders(lastSeed);
            if (headersFromLastSeed.length) setTableHeaders(headersFromLastSeed);
          }
          seeded = true;
        }
      }
    } catch (e) {
      console.warn('Failed to load pending results seed from sessionStorage', e);
    }

    const interval = selectedProjectId ? setInterval(() => {
      getProjectStatus();
    }, 10000) : null;

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [selectedProjectId, selectedProject?.name]);

  // Fetch results when switching to results tab (skip while editing)
  useEffect(() => {
    if (tabValue === 0 && selectedProjectId && !isEditing) {
      fetchExtractionResults();
    }
  }, [tabValue, selectedProjectId, isEditing]);

  // Also fetch results when docStatus updates (polling) so cell values fill in, but skip while editing
  useEffect(() => {
    if (tabValue === 0 && selectedProjectId && !isEditing) {
      fetchExtractionResults();
    }
  }, [docStatus, tabValue, selectedProjectId, isEditing]);

  // Continuous polling for extraction results while on Results tab and not editing
  useEffect(() => {
    if (!(tabValue === 0 && selectedProjectId && !isEditing)) return;
    const interval = setInterval(() => {
      fetchExtractionResults();
    }, 7000);
    return () => clearInterval(interval);
  }, [tabValue, selectedProjectId, isEditing]);

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

  // Helper to read a field value from extractionResults for a given docId
  const getFieldValueByDocId = (docId, fieldName) => {
    const row = extractionResults.find(d => (d.doc_id || d.id) === docId);
    if (!row) return null;
    return getFieldValue(row, fieldName);
  };

  const getSourcePages = (doc, fieldName) => {
    const field = doc?.results?.[fieldName];
    if (!field) return [];
    if (Array.isArray(field.source_pages) && field.source_pages.length) return field.source_pages;
    if (Array.isArray(field.chunks)) {
      const pages = [...new Set(field.chunks.map((c) => c?.page).filter((p) => p !== undefined && p !== null))];
      return pages;
    }
    return [];
  };

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

  // View fields selection dialog handlers
  const getAllAvailableFields = () => {
    const headersFromResults = extractTableHeaders(extractionResults);
    const union = new Set([...(headersFromResults || []), ...(tableHeaders || [])]);
    return Array.from(union).sort();
  };

  const openViewFields = () => {
    setTempSelectedFields([...(tableHeaders || [])]);
    setViewFieldsOpen(true);
  };

  const toggleTempField = (field) => {
    setTempSelectedFields((prev) => {
      const set = new Set(prev);
      if (set.has(field)) set.delete(field);
      else set.add(field);
      return Array.from(set);
    });
  };

  const applyViewFields = () => {
    const selected = Array.isArray(tempSelectedFields) ? tempSelectedFields : [];
    setTableHeaders(selected);
    try {
      if (selectedProjectId) {
        const map = JSON.parse(sessionStorage.getItem('project_fields_map')) || {};
        map[selectedProjectId] = selected;
        sessionStorage.setItem('project_fields_map', JSON.stringify(map));
      }
      if (selectedProject?.name) {
        const byName = JSON.parse(sessionStorage.getItem('project_fields_map_by_name')) || {};
        byName[selectedProject.name] = selected;
        sessionStorage.setItem('project_fields_map_by_name', JSON.stringify(byName));
      }
    } catch (e) {
      console.warn('Failed to persist selected fields', e);
    }
    setViewFieldsOpen(false);
  };

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
                t.palette.mode === "dark"
                  ? t.palette.background.paper
                  : "#fff",
              // color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#202124"),
              color: (t) =>
                t.palette.mode === "dark"
                  ? t.palette.text.primary
                  : "#111827",
              boxShadow: (t) =>
                t.palette.mode === "dark"
                  ? "inset 0 0 0 1px rgba(255,255,255,0.08)"
                  : "0 0 0 1px rgba(0,0,0,0.1)",
            },
            "& .MuiTab-root:hover": {
              backgroundColor: (t) =>
                t.palette.mode === "dark"
                  ? t.palette.action.selected
                  : "#f1f3f4",
              color: (t) =>
                t.palette.mode === "dark"
                  ? t.palette.text.primary
                  : "#111827",
            },
          }}
        >
          <Tab label="Results" />
          <Tab label="Documents" />
        </Tabs>
      </Box>

      {/* Results Tab */}
      <TabPanel value={tabValue} index={0}>
        <Box
          sx={{
            p: 3,
            width: "100%",
            backgroundColor: (t) =>
              t.palette.mode === "dark" ? t.palette.background.default : "#f5f6f7",
            borderRadius: 2,
          }}
        >
          <Typography
            variant="h6"
            gutterBottom
            sx={{
              fontWeight: 550,
              fontSize: 24,
              color: (theme) =>
                theme.palette.mode === "dark" ? "white" : "#282C34",
              "&.Mui-selected": {
                color: (theme) =>
                  theme.palette.mode === "dark" ? "white" : "#282C34",
              },
            }}
          >
            Extraction Results
          </Typography>
          <Box
            sx={{
              mb: 3,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {loadingResults
                ? "Loading results..."
                : isEditing
                  ? "Edit mode: modify fields and click Save All"
                  : "Click Edit to modify results"}
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              {!isEditing ? (
                <>
                  <Button
                    variant="contained"
                    onClick={startGlobalEdit}
                    disabled={
                      extractionResults.length === 0 || tableHeaders.length === 0
                    }
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<VisibilityOutlinedIcon />}
                    onClick={openViewFields}
                    disabled={extractionResults.length === 0}
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    View
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<UploadOutlined />}
                    onClick={() => openExportDialog('excel')}
                    disabled={extractionResults.length === 0}
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    Export Excel
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<DescriptionIcon />}
                    onClick={() => openExportDialog('word')}
                    disabled={extractionResults.length === 0}
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    Export Word
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="contained"
                    color="success"
                    onClick={saveAllEdits}
                    disabled={savingEdit}
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    Save All
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    onClick={cancelGlobalEdit}
                    disabled={savingEdit}
                    sx={{
                      textTransform: "none",
                      fontWeight: 600,
                      borderRadius: "6px",
                      px: 2,
                      py: 1,
                    }}
                  >
                    Cancel
                  </Button>
                </>
              )}
            </Box>
          </Box>

          {tableHeaders.length === 0 ? (
            <Box sx={{ textAlign: "center", p: 3 }}>
              <Typography color="text.secondary" gutterBottom>
                No fields configured yet for this project.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Configure fields during project creation to see results.
              </Typography>
            </Box>
          ) : (
            <TableContainer
              component={Paper}
              sx={{
                boxShadow: 1,
                overflowX: 'auto',
                bgcolor: (t) => t.palette.background.paper,
                border: (t) => `1px solid ${t.palette.divider}`,
                borderRadius: 1,
                scrollbarWidth: 'thin',
                '&::-webkit-scrollbar': { height: 6 },
                '&::-webkit-scrollbar-thumb': {
                  backgroundColor: (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.25)',
                  borderRadius: 8,
                },
                '&::-webkit-scrollbar-track': { backgroundColor: 'transparent' },
              }}
            >
              <Table stickyHeader>
                <TableHead
                  sx={{
                    backgroundColor: (t) => t.palette.mode === 'dark' ? t.palette.background.default : '#eef2f7',
                    '& .MuiTableCell-root': {
                      color: (t) => t.palette.mode === 'dark' ? t.palette.text.primary : '#111827',
                      borderBottom: (t) => `1px solid ${t.palette.divider}`,
                      fontWeight: 700,
                      fontSize: '0.9rem',
                      py: 1.5,
                    },
                  }}
                >
                  <TableRow>
                    <TableCell sx={{ minWidth: 220, position: 'sticky', left: 0, zIndex: 3, backgroundColor: (t) => t.palette.mode === 'dark' ? t.palette.background.default : '#eef2f7' }}>Field</TableCell>
                    {extractionResults.map((doc) => (
                      <TableCell key={doc.doc_id || doc.id} sx={{ minWidth: 220 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <DescriptionIcon fontSize='small' color='action' />
                          <Tooltip title={doc.fileName} arrow>
                            <Typography
                              variant='body2'
                              sx={{
                                fontFamily: 'monospace',
                                fontWeight: 500,
                                display: 'block',
                                maxWidth: '40ch',
                                whiteSpace: 'normal',
                                overflowWrap: 'anywhere',
                                wordBreak: 'break-word',
                                maxHeight: '10rem',
                                overflowY: 'auto',
                              }}
                            >
                              {doc.fileName}
                            </Typography>
                          </Tooltip>
                        </Box>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tableHeaders.map((header) => (
                    <TableRow key={header}>
                      <TableCell sx={{ fontWeight: 700, position: 'sticky', left: 0, zIndex: 2, backgroundColor: (t) => t.palette.background.paper }}>{formatFieldName(header)}</TableCell>
                      {extractionResults.map((doc) => (
                        <TableCell key={`${doc.doc_id || doc.id}-${header}`}>
                          {isEditing && header !== 'doc_name' ? (
                            <TextField
                              size='small'
                              fullWidth
                              value={(editedValues[getRowKey(doc)] && editedValues[getRowKey(doc)][header]) ?? String(getFieldValue(doc, header))}
                              onChange={(e) => handleFieldChange(getRowKey(doc), header, e.target.value)}
                              disabled={savingEdit}
                            />
                          ) : (
                              <Box>
                                <Typography
                                  variant='body2'
                                  sx={{
                                    fontStyle: getFieldValue(doc, header) === 'NULL' ? 'italic' : 'normal',
                                    color: getFieldValue(doc, header) === 'NULL' ? 'text.secondary' : 'text.primary',
                                    display: 'block',
                                    maxWidth: '30ch',
                                    whiteSpace: 'normal',
                                    overflowWrap: 'anywhere',
                                    wordBreak: 'break-word',
                                    maxHeight: '12rem',
                                    overflowY: 'auto',
                                  }}
                                >
                                  {getFieldValue(doc, header)}
                                </Typography>
                                {getSourcePages(doc, header).length > 0 && (
                                  <Box sx={{ mt: 0.5, display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: 0.5, rowGap: 0.5 }}>
                                    <Typography variant='caption' sx={{ mr: 0.5, color: 'text.secondary' }}>Pages:</Typography>
                                    {getSourcePages(doc, header).map((p) => (
                                      <Button key={p} size='small' variant='text' onClick={() => handlePageClick(p)} sx={{ minWidth: 0, px: 1 }}>
                                        {p}
                                      </Button>
                                    ))}
                                  </Box>
                                )}
                                {doc?.results?.[header]?.explanation && (
                                  <Box sx={{ mt: 0.5, display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 0.5, rowGap: 0.5 }}>
                                    <Typography variant='caption' sx={{ mr: 0.5, color: 'text.secondary' }}>Explanation:</Typography>
                                    <Tooltip
                                      arrow
                                      title={
                                        <Box sx={{ maxWidth: 480, maxHeight: 300, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                                          {String(doc.results[header].explanation)}
                                        </Box>
                                      }
                                    >
                                      <IconButton 
                                        size='small' 
                                        sx={{ p: 0.25 }}
                                        onClick={() => handleOpenExplanation(
                                          `${formatFieldName(header)} - ${doc.fileName || 'Document'}`,
                                          String(doc.results[header].explanation)
                                        )}
                                      >
                                        <VisibilityOutlinedIcon fontSize='inherit' />
                                      </IconButton>
                                    </Tooltip>
                                  </Box>
                                )}
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

      {/* Export Fields Dialog */}
      <Dialog
        open={exportFieldsOpen}
        onClose={() => setExportFieldsOpen(false)}
        aria-labelledby="export-fields-dialog-title"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle id="export-fields-dialog-title">
          {exportMode === 'word' ? 'Select fields to export (Word)' : 'Select fields to export (Excel)'}
        </DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose which fields to include in the exported file.
          </Typography>
          <FormGroup>
            {getAllAvailableFields().map((field) => (
              <FormControlLabel
                key={`export-${field}`}
                control={
                  <Checkbox
                    checked={tempExportFields.includes(field)}
                    onChange={() => toggleTempExportField(field)}
                  />
                }
                label={formatFieldName(field)}
              />
            ))}
          </FormGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExportFieldsOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={applyExport} variant="contained" disabled={tempExportFields.length === 0}>Export</Button>
        </DialogActions>
      </Dialog>

      {/* Explanation Dialog */}
      <Dialog
        open={viewFieldsOpen}
        onClose={() => setViewFieldsOpen(false)}
        aria-labelledby="view-fields-dialog-title"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle id="view-fields-dialog-title">Select fields to view</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose which fields should be visible in the results table.
          </Typography>
          <FormGroup>
            {getAllAvailableFields().map((field) => (
              <FormControlLabel
                key={field}
                control={
                  <Checkbox
                    checked={tempSelectedFields.includes(field)}
                    onChange={() => toggleTempField(field)}
                  />
                }
                label={formatFieldName(field)}
              />
            ))}
          </FormGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewFieldsOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={applyViewFields} variant="contained" disabled={tempSelectedFields.length === 0}>Apply</Button>
        </DialogActions>
      </Dialog>

      {/* Explanation Dialog */}
      <Dialog
        open={explanationDialog.open}
        onClose={handleCloseExplanation}
        aria-labelledby="explanation-dialog-title"
        maxWidth="md"
        fullWidth
      >
        <DialogTitle id="explanation-dialog-title">
          {explanationDialog.title}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {explanationDialog.content}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseExplanation} color="primary">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Processing Tab */}
      <TabPanel value={tabValue} index={1}>
        <Box 
          sx={{ 
            p: 3, 
            width: '100%',
            backgroundColor: (t) => t.palette.mode === 'dark' ? t.palette.background.default : "#f5f6f7",
            borderRadius: 2, 
            display: 'flex', 
            flexDirection: 'column', 
            maxHeight: '65vh', 
            overflow: 'hidden'
          }}
        >
            <Typography 
              variant="h6" 
              sx={{ 
                fontWeight: 500, 
                color: (theme) => theme.palette.mode === "dark" ? "white" : "#282C34",
                "&.Mui-selected": {
                  color: (theme) => theme.palette.mode === "dark" ? "white" : "#282C34",
                } 
              }}
            >
              Processing Queue
            </Typography>
            
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Real-time status of document processing
          </Typography>
          <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setAddDocumentOpen(true)}
              sx={{
                textTransform: 'none',
                fontWeight: 500,
                borderRadius: '6px',
                px: 2,
                py: 1,
              }}
            >
              Add Document
            </Button>
         
        </Box>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minHeight: 0, overflowY: 'auto', scrollbarWidth: 'thin', '&::-webkit-scrollbar': { width: 6 }, '&::-webkit-scrollbar-thumb': { backgroundColor: (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.25)', borderRadius: 8 }, '&::-webkit-scrollbar-track': { backgroundColor: 'transparent' } }}>
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
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {getStatusChip(item.status)}
                        <Tooltip title="Regenerate" arrow>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => handleRegenerate(item)}
                              disabled={Boolean(regenerating[item.doc_id || item.id])}
                              sx={{ ml: 0.5 }}
                            >
                              <AutorenewIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Box>
                    </Box>

                    {normalizeStatus(item.status) === "processing" && (
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
      {/* Add Document Modal */}
      <AddDocumentModal
        open={addDocumentOpen}
        onClose={() => setAddDocumentOpen(false)}
        onAddDocument={handleAddDocument}
        projectId={selectedProjectId}
      />
    </Box>
  );
};

export default Dashboard;