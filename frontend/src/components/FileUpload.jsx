import React from 'react';
import {
  Button,
  List,
  ListItem,
  ListItemText,
  Typography,
  Paper,
  Box,
  IconButton,
  Divider,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import DeleteIcon from '@mui/icons-material/Delete';

const FileUpload = ({ files, onFilesSelected }) => {
  const handleFileChange = (event) => {
    const selectedFiles = Array.from(event.target.files);
    onFilesSelected([...files, ...selectedFiles]);
  };

  const handleDeleteFile = (indexToDelete) => {
    const updatedFiles = files.filter((_, index) => index !== indexToDelete);
    onFilesSelected(updatedFiles);
  };

  return (
    <Paper elevation={3} sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        Upload Documents
      </Typography>

      <Button
        variant="contained"
        component="label"
        startIcon={<UploadFileIcon />}
        fullWidth
      >
        Select Files
        <input
          type="file"
          hidden
          multiple
          onChange={handleFileChange}
        />
      </Button>

      {files.length > 0 && (
        <Box mt={2}>
          <Typography variant="subtitle1" gutterBottom>
            Selected Files:
          </Typography>

          <List
            dense
            sx={{
              maxHeight: 300, 
              overflowY: 'auto',
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
            }}
          >
            {files.map((file, index) => (
              <React.Fragment key={index}>
                <ListItem
                  secondaryAction={
                    <IconButton
                      edge="end"
                      aria-label="delete"
                      onClick={() => handleDeleteFile(index)}
                    >
                      <DeleteIcon />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={file.name}
                    secondary={`${(file.size / 1024).toFixed(2)} KB`}
                  />
                </ListItem>
                {index < files.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
        </Box>
      )}
    </Paper>
  );
};

export default FileUpload;
