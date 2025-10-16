// import React from 'react';
// import { DataGrid } from '@mui/x-data-grid';
// import { Paper, Typography, Box, Button } from '@mui/material';
// import DownloadIcon from '@mui/icons-material/Download';

// const ResultsDisplay = ({ data, loading, onDataUpdate }) => {
//   const handleDownload = (row) => {
//     console.log('Downloading:', row.documentName);

//     // Example (if file URL is available in row.fileUrl):
//     // const link = document.createElement('a');
//     // link.href = row.fileUrl;
//     // link.download = row.documentName;
//     // link.click();
//   };

//   const columns = [
//     { field: 'id', headerName: 'ID', width: 90 },
//     {
//       field: 'documentName',
//       headerName: 'Document Name',
//       width: 250,
//       editable: false,
//     },
//     {
//       field: 'keyPoint',
//       headerName: 'Key Point',
//       width: 200,
//       editable: false,
//     },
//     {
//       field: 'value',
//       headerName: 'Extracted Value',
//       flex: 1,
//       editable: true,
//     },
//     {
//       field: 'download',
//       headerName: 'Download',
//       width: 150,
//       sortable: false,
//       filterable: false,
//       renderCell: (params) => (
//         <Button
//           variant="contained"
//           size="small"
//           startIcon={<DownloadIcon />}
//           onClick={() => handleDownload(params.row)}
//         >
//           Download
//         </Button>
//       ),
//     },
//   ];

//   const handleProcessRowUpdate = (newRow) => {
//     onDataUpdate(newRow);
//     return newRow;
//   };

//   return (
//     <Paper
//       elevation={0}
//       sx={{
//         p: 3,
//         mt: 3,
//         height: 500,
//         width: "100%",
//         borderRadius: 3,
//         backgroundColor:
//           theme.palette.mode === "dark"
//             ? "rgba(255, 255, 255, 0.05)" 
//             : "rgba(0, 0, 0, 0.03)", 
//         border: `1px solid ${
//           theme.palette.mode === "dark"
//             ? "rgba(255,255,255,0.08)"
//             : "rgba(0,0,0,0.08)"
//         }`,
//         boxShadow:
//           theme.palette.mode === "dark"
//             ? "0 0 10px rgba(0,0,0,0.4)"
//             : "0 0 10px rgba(0,0,0,0.08)",
//         transition: "background-color 0.3s ease, box-shadow 0.3s ease",
//       }}
    
//     >
//       <Typography variant="h6" gutterBottom>
//         Extraction Results
//       </Typography>
//       <Box sx={{ height: 'calc(100% - 48px)', width: '100%' }}>
//         <DataGrid
//           rows={data}
//           columns={columns}
//           loading={loading}
//           processRowUpdate={handleProcessRowUpdate}
//           onProcessRowUpdateError={(error) => console.error(error)}
//           pageSize={10}
//           rowsPerPageOptions={[5, 10, 20]}
//           checkboxSelection
//           disableSelectionOnClick
//         />
//       </Box>
//     </Paper>
//   );
// };

// export default ResultsDisplay;



import React, { useEffect, useState } from "react";
import { getDocumentResults } from "../api/api";
import {
  DataGrid
} from "@mui/x-data-grid";
import {
  Paper,
  Typography,
  Box,
  Button,
  Skeleton,
  Stack,
  useTheme
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";

const ResultsDisplay = ({ projectId, uploadedDocsCount }) => {
  const theme = useTheme();
  const [data, setData] = useState([]);
  const [columns, setColumns] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchResults = async () => {
    try {
      setLoading(true);
      const allRows = [];

      for (let i = 1; i <= uploadedDocsCount; i++) {
        const docId = `${projectId}_doc_${i}`;
        const result = await getDocumentResults(projectId, docId);

        if (result?.results) {
          const fields = Object.values(result.results);

          fields.forEach((field, index) => {
            allRows.push({
              id: `${docId}_${index}`,
              documentName: docId,
              fieldName: field.field_name,
              value: field.value,
              status: field.status,
              confidence: field.confidence ?? "-",
            });
          });
        }
      }

      if (allRows.length > 0) {
        const dynamicColumns = Object.keys(allRows[0])
          .filter((key) => key !== "id") 
          .map((key) => ({
            field: key,
            headerName: key.replace(/([A-Z])/g, " $1").replace(/^./, (str) => str.toUpperCase()),
            flex: 1,
          }));

        // Add download button column
        dynamicColumns.push({
          field: "download",
          headerName: "Download",
          width: 150,
          renderCell: (params) => (
            <Button
              variant="contained"
              size="small"
              startIcon={<DownloadIcon />}
              onClick={() => console.log("Download:", params.row.documentName)}
            >
              Download
            </Button>
          ),
        });

        setColumns(dynamicColumns);
      }

      setData(allRows);
    } catch (error) {
      console.error("Error fetching results:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId && uploadedDocsCount > 0) {
      fetchResults();
    }
  }, [projectId, uploadedDocsCount]);

  const ShimmerTable = () => (
    <Stack spacing={1}>
      {Array.from({ length: 6 }).map((_, idx) => (
        <Stack key={idx} direction="row" spacing={2}>
          <Skeleton variant="rectangular" width="15%" height={40} />
          <Skeleton variant="rectangular" width="20%" height={40} />
          <Skeleton variant="rectangular" width="40%" height={40} />
          <Skeleton variant="rectangular" width="20%" height={40} />
        </Stack>
      ))}
    </Stack>
  );

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
      }}
    >
      <Typography variant="h6" gutterBottom>
        Extraction Results
      </Typography>

      <Box sx={{ height: "calc(100% - 48px)", width: "100%" }}>
        {loading ? (
          <ShimmerTable />
        ) : (
          <DataGrid
            rows={data}
            columns={columns}
            pageSize={10}
            rowsPerPageOptions={[5, 10, 20]}
            disableSelectionOnClick
            checkboxSelection
          />
        )}
      </Box>
    </Paper>
  );
};

export default ResultsDisplay;
