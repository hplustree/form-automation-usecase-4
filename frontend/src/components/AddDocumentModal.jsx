import React, { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  IconButton,
  Paper,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { Close as CloseIcon } from "@mui/icons-material";
import { LuUpload } from "react-icons/lu";

const AddDocumentModal = ({ open, onClose, onAddDocument }) => {
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const mergeFiles = (prevFiles, newFiles) => {
    const map = new Map();
    [...prevFiles, ...newFiles].forEach((f) => {
      const key = `${f.name}_${f.size}_${f.lastModified}`;
      if (!map.has(key)) map.set(key, f);
    });
    return Array.from(map.values());
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
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setUploadedFiles((prev) => mergeFiles(prev, files));
    e.target.value = null;
  };

  const handleSubmit = () => {
    // TODO: Add API integration here
    console.log("Files to upload:", uploadedFiles);
    onAddDocument(uploadedFiles);
    setUploadedFiles([]);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      fullScreen={isMobile}
    >
      <DialogTitle>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">Add Documents</Typography>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        <Paper
          variant="outlined"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          sx={{
            p: 4,
            border: dragOver ? `2px dashed ${theme.palette.primary.main}` : "2px dashed #ccc",
            backgroundColor: dragOver ? alpha(theme.palette.primary.light, 0.1) : "transparent",
            textAlign: "center",
            cursor: "pointer",
            transition: "all 0.3s ease",
            '&:hover': {
              borderColor: theme.palette.primary.main,
              backgroundColor: alpha(theme.palette.primary.light, 0.05),
            },
          }}
          onClick={() => document.getElementById('file-upload')?.click()}
        >
          <input
            type="file"
            id="file-upload"
            style={{ display: 'none' }}
            multiple
            onChange={handleFileSelect}
          />
          <Box display="flex" flexDirection="column" alignItems="center" gap={2}>
            <LuUpload size={48} color={dragOver ? "#1976d2" : "#9e9e9e"}
                style={{
                  marginBottom: 16,
                  transition: "color 0.2s ease-in-out",
                }} />
            <Typography variant="h6">Drag & drop files here</Typography>
            <Typography variant="body2" color="text.secondary">
              or click to browse files
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Supported formats: PDF, JPG, PNG, TIFF
            </Typography>
          </Box>
        </Paper>

        {uploadedFiles.length > 0 && (
          <Box mt={3}>
            <Typography variant="subtitle1" gutterBottom>
              Selected Files ({uploadedFiles.length}):
            </Typography>
            <Box
              sx={{
                maxHeight: 200,
                overflowY: "auto",
                border: "1px solid #eee",
                borderRadius: 1,
                p: 1,
              }}
            >
              {uploadedFiles.map((file, index) => (
                <Box
                  key={`${file.name}-${file.size}`}
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                  py={1}
                  px={2}
                  sx={{
                    backgroundColor: index % 2 === 0 ? 'action.hover' : 'background.paper',
                    borderRadius: 1,
                    mb: 1,
                  }}
                >
                  <Typography variant="body2" noWrap sx={{ maxWidth: '80%' }}>
                    {file.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {(file.size / 1024).toFixed(1)} KB
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          color="primary"
          disabled={uploadedFiles.length === 0}
        >
          Upload Documents
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AddDocumentModal;
