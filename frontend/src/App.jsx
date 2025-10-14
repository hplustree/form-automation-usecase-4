import React, { useState } from "react";
import { Box, CssBaseline, useMediaQuery, useTheme } from "@mui/material";

import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import CreateProjectModal from "./components/CreateProjectModal";
import { projects as initialProjects } from "./data/mockData";

const DRAWER_WIDTH = 281;

function App() {
  const [projects, setProjects] = useState(initialProjects);
  const [selectedProject, setSelectedProject] = useState(initialProjects[0]); 
  const [sidebarOpen, setSidebarOpen] = useState(true); 
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  const handleMenuClick = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const handleProjectSelect = (project) => {
    setSelectedProject(project);
    if (isMobile) {
      setSidebarOpen(false);
    }
  };

  // Close sidebar on mobile by default
  React.useEffect(() => {
    if (isMobile) {
      setSidebarOpen(false);
    } else {
      setSidebarOpen(true);
    }
  }, [isMobile]);

  const handleCreateProject = (newProject) => {
    setProjects((prev) => [...prev, newProject]);
    setSelectedProject(newProject);
  };

  const handleCreateProjectOpen = () => {
    setCreateProjectOpen(true);
    if (isMobile) {
      setSidebarOpen(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <CssBaseline />
      {/* Header aligned with content area */}
      {/* <Box> */}
      <Header
        onMenuClick={handleMenuClick}
        sidebarOpen={sidebarOpen}
        isMobile={isMobile}
        drawerWidth={DRAWER_WIDTH}
      />
      {/* </Box> */}
      {/* spacer for fixed AppBar height */}
      <Box sx={(t) => ({ ...t.mixins.toolbar })} />

      {/* Main container with sidebar and content */}
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Sidebar */}
        <Sidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          selectedProject={selectedProject}
          onProjectSelect={handleProjectSelect}
          onCreateProject={handleCreateProjectOpen}
          isMobile={isMobile}
        />

        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 3,
            overflow: "auto",
            transition: theme.transitions.create("margin", {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.leavingScreen,
            }),
            marginLeft: !isMobile && sidebarOpen ? 0 : 0,
            backgroundColor: theme.palette.background.paper,
          }}
        >
          {/* <Dashboard selectedProject={selectedProject} /> */}
          <Dashboard
            selectedProject={selectedProject}
            onMenuClick={handleMenuClick}
            sidebarOpen={sidebarOpen}
          />
        </Box>
      </Box>

      {/* Create Project Modal */}
      <CreateProjectModal
        open={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
        onCreateProject={handleCreateProject}
      />
    </Box>
  );
}

export default App;
