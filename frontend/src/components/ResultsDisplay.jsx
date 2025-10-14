import React from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Paper, Typography, Box, Button } from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';

const ResultsDisplay = ({ data, loading, onDataUpdate }) => {
  const handleDownload = (row) => {
    console.log('Downloading:', row.documentName);

    // Example (if file URL is available in row.fileUrl):
    // const link = document.createElement('a');
    // link.href = row.fileUrl;
    // link.download = row.documentName;
    // link.click();
  };

  const columns = [
    { field: 'id', headerName: 'ID', width: 90 },
    {
      field: 'documentName',
      headerName: 'Document Name',
      width: 250,
      editable: false,
    },
    {
      field: 'keyPoint',
      headerName: 'Key Point',
      width: 200,
      editable: false,
    },
    {
      field: 'value',
      headerName: 'Extracted Value',
      flex: 1,
      editable: true,
    },
    {
      field: 'download',
      headerName: 'Download',
      width: 150,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Button
          variant="contained"
          size="small"
          startIcon={<DownloadIcon />}
          onClick={() => handleDownload(params.row)}
        >
          Download
        </Button>
      ),
    },
  ];

  const handleProcessRowUpdate = (newRow) => {
    onDataUpdate(newRow);
    return newRow;
  };

  return (
    <Paper
      elevation={0}
      sx={{
        p: 3,
        mt: 3,
        height: 500,
        width: "100%",
        borderRadius: 3,
        backgroundColor:
          theme.palette.mode === "dark"
            ? "rgba(255, 255, 255, 0.05)" 
            : "rgba(0, 0, 0, 0.03)", 
        border: `1px solid ${
          theme.palette.mode === "dark"
            ? "rgba(255,255,255,0.08)"
            : "rgba(0,0,0,0.08)"
        }`,
        boxShadow:
          theme.palette.mode === "dark"
            ? "0 0 10px rgba(0,0,0,0.4)"
            : "0 0 10px rgba(0,0,0,0.08)",
        transition: "background-color 0.3s ease, box-shadow 0.3s ease",
      }}
    
    >
      <Typography variant="h6" gutterBottom>
        Extraction Results
      </Typography>
      <Box sx={{ height: 'calc(100% - 48px)', width: '100%' }}>
        <DataGrid
          rows={data}
          columns={columns}
          loading={loading}
          processRowUpdate={handleProcessRowUpdate}
          onProcessRowUpdateError={(error) => console.error(error)}
          pageSize={10}
          rowsPerPageOptions={[5, 10, 20]}
          checkboxSelection
          disableSelectionOnClick
        />
      </Box>
    </Paper>
  );
};

export default ResultsDisplay;
