import React, { useState } from "react";
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
  useMediaQuery,
  useTheme,
  Button,
  CircularProgress,
  Divider
} from "@mui/material";
import {
  Description as DescriptionIcon,
  CheckCircle as CheckCircleIcon,
  Schedule as ScheduleIcon,
  HourglassEmpty as HourglassEmptyIcon,
  PlayArrow as PlayArrowIcon,
} from "@mui/icons-material";
import { processingQueue, extractionResults } from "../data/mockData";
import InsertDriveFileOutlinedIcon from '@mui/icons-material/InsertDriveFileOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
};



const Dashboard = ({ selectedProject, onMenuClick, sidebarOpen }) => {
  const [tabValue, setTabValue] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processedItems, setProcessedItems] = useState(new Set());
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const simulateProcessing = () => {
    setIsProcessing(true);
    // Simulate processing delay
    setTimeout(() => {
      setIsProcessing(false);
      // Add a new processed item (just for demo)
      setProcessedItems((prev) => new Set([...prev, Date.now()]));
    }, 2000);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "completed":
        return <CheckCircleIcon color="success" />;
      case "processing":
        return <ScheduleIcon color="warning" />;
      case "pending":
        return <HourglassEmptyIcon color="action" />;
      default:
        return <HourglassEmptyIcon color="action" />;
    }
  };

  const handleViewResults = () => {
    setTabValue(0);
  }

  const getStatusChip = (status) => {
    const statusConfig = {
      completed: {
        label: "Completed",
        color: "success",
        sx: {
          backgroundColor: theme.palette.success.light,
          // backgroundColor: "#21C45D1A",
          color: theme.palette.success.dark,
          fontWeight: 600,
        },
      },
      processing: {
        label: "Processing",
        color: "warning",
        sx: {
          backgroundColor: theme.palette.warning.light,
          // backgroundColor: "#F59F0A1A",
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
      {/* Current Project Indicator */}
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <IconButton
          onClick={onMenuClick}
          sx={{
            mr: 1,
            // p: 1,
            // borderRadius: 1,
            // border: "1px solid",
            // borderColor: "divider",
            // backgroundColor: "action.hover",
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
        {/* Current Project Indicator */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            color: "text.secondary",
            fontSize: "0.875rem",
          }}
        >
          {/* <Box component="span" sx={{ fontSize: '1.2rem' }}>📁</Box> */}
          <Typography variant="body2" color="text.secondary">
            Current Project
          </Typography>
        </Box>
      </Box>

      {/* <hr style={{ borderColor: "rgba(0, 0, 0, 0.12)" }} /> */}
      <Divider sx={{ mb: 2 }} />

      {/* Project Header */}
      <Box sx={{ mb: 3 }}>
        <Typography
          variant="h4"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 500, color: "text.primary" }}
        >
          {selectedProject.name}
        </Typography>
        <Typography variant="body1" color="text.secondary">
          View extraction results and processing status
        </Typography>
      </Box>

      {/* Tabs */}
      <Box
        sx={{
          borderBottom: 1,
          borderColor: "divider",
          position: "sticky",
          top: 0,
          zIndex: 1,
          bgcolor: "background.paper",
        }}
      >
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          sx={{
            "& .MuiTabs-indicator": {
              display: "none", // Hide the default indicator
            },
            "& .MuiTab-root": {
              minHeight: 48,
              textTransform: "none",
              fontWeight: 600,
              px: 3,
              borderRadius: 1,
              marginRight: 1,
              color: "text.secondary",
            },
            "& .Mui-selected": {
              color: "text.primary",
              backgroundColor: (t) => alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.24 : 0.12),
              border: "1px solid",
              borderColor: (t) => alpha(t.palette.primary.main, 0.3),
            },
          }}
        >
          <Tab label="Results" />
          <Tab label="Processing" />
        </Tabs>
      </Box>

      {/* Results Tab */}
      <TabPanel value={tabValue} index={0}>
        <Box>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
            Extraction Results
          </Typography>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: 3,
            }}
          >
            <Typography variant="body2" color="text.secondary">
              Click any cell to edit extracted data
            </Typography>
          </Box>

          <TableContainer
            component={Paper}
            sx={{
              boxShadow: 1,
              overflowX: "auto",
              bgcolor: "background.paper",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
            }}
          >
            <Table>
              <TableHead
                sx={{
                  backgroundColor: (t) =>
                    t.palette.mode === "dark"
                      ? alpha(t.palette.common.white, 0.06)
                      : alpha(t.palette.common.black, 0.04),
                  "& .MuiTableCell-root": {
                    color: "text.primary",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                  },
                }}
              >
                <TableRow>
                  <TableCell sx={{ fontWeight: 600, minWidth: 200 }}>
                    File Name
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 600,
                      minWidth: 150,
                      display: { xs: "none", sm: "table-cell" },
                    }}
                  >
                    Company
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600, minWidth: 120 }}>
                    Date
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600, minWidth: 100 }}>
                    Amount
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 600,
                      minWidth: 120,
                      display: { xs: "none", md: "table-cell" },
                    }}
                  >
                    Invoice
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {extractionResults.map((row) => (
                  <TableRow
                    key={row.id}
                    hover
                    sx={{
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      "&:hover": {
                        backgroundColor: (t) =>
                          t.palette.mode === "dark"
                            ? alpha(t.palette.common.white, 0.04)
                            : alpha(t.palette.common.black, 0.04),
                        cursor: "pointer",
                      },
                    }}
                  >
                    <TableCell>
                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 1 }}
                      >
                        <DescriptionIcon fontSize="small" color="action" />
                        <Typography
                          variant="body2"
                          sx={{
                            fontFamily: "monospace",
                            // color: "primary.main",
                            fontWeight: 500,
                          }}
                        >
                          {row.fileName}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell
                      sx={{ display: { xs: "none", sm: "table-cell" } }}
                    >
                      <Typography variant="body2" color="text.primary">
                        {row.company}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.primary">
                        {row.date}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        color="text.primary"
                        sx={{ fontWeight: 600 }}
                      >
                        {row.amount}
                      </Typography>
                    </TableCell>
                    <TableCell
                      sx={{ display: { xs: "none", md: "table-cell" } }}
                    >
                      <Typography variant="body2" color="text.primary">
                        {row.invoice}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      </TabPanel>

      {/* Processing Tab */}
      <TabPanel value={tabValue} index={1}>
        <Box>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
            Processing Queue
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Real-time status of document processing
          </Typography>

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {processingQueue.map((item) => (
              <Card
                key={item.id}
                sx={{
                  transition: "all 0.2s ease-in-out",
                  "&:hover": {
                    transform: "translateY(-2px)",
                  },
                }}
              >
                <CardContent sx={{ pb: 2 }}>
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
                      {/* {getStatusIcon(item.status)} */}
                      <InsertDriveFileOutlinedIcon />
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography
                        variant="body1"
                        sx={{
                          fontFamily: "monospace",
                          fontWeight: 600,
                          color: theme.palette.text.primary,
                        }}
                      >
                        {item.fileName}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Document processing
                      </Typography>
                    </Box>
                    {getStatusChip(item.status)}
                  </Box>

                  {item.status === "processing" && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                      <LinearProgress
                        variant="determinate"
                        value={item.progress}
                        sx={{
                          flex: 1,
                          height: 8,
                          borderRadius: 4,
                          "& .MuiLinearProgress-bar": {
                            borderRadius: 4,
                          },
                        }}
                      />
                      <Typography
                        variant="body2"
                        sx={{
                          color: theme.palette.text.secondary,
                          fontWeight: 600,
                          minWidth: 40,
                        }}
                      >
                        {item.progress}%
                      </Typography>
                    </Box>
                  )}
                </CardContent>
              </Card>
            ))}
          </Box>
        </Box>
      </TabPanel>

      {tabValue === 1 && (
        <Box
          sx={{
            display: "flex",
            justifyContent: "flex-end",
            mt: 3, // space above
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
