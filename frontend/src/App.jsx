import React, { useState } from "react";
import { Box, CssBaseline, useMediaQuery, useTheme } from "@mui/material";

import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import CreateProjectModal from "./components/CreateProjectModal";
// import { projects as initialProjects } from "./data/mockData";
import {getProjectIdByName, getProjects} from "./api/api";

const DRAWER_WIDTH = 319;

function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(); 
  const [selectedProjectId , setSelectedProjectId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true); 
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  const handleMenuClick = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const handleProjectSelect = (project) => {
    setSelectedProject(project);
    const projectId = getProjectIdByName(project.name);
    setSelectedProjectId(projectId);

    
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

  // Fetch projects on initial load
  React.useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await getProjects(0, 100);
        const list = Array.isArray(res)
          ? res
          : (res?.items || res?.data || res?.results || []);

        const mapped = list.map((p) => ({
          id: p.project_id ?? p.id ?? p._id ?? p.name,
          name: p.project_name ?? p.name ?? `Project ${p.project_id ?? p.id ?? ""}`,
          documentCount: p.total_documents ?? p.documents?.length ?? p.document_count ?? p.doc_count ?? 0,
          createdAt: p.created_at ?? p.createdAt ?? p.created ?? null,
          status: p.status,
          processedDocuments: p.processed_documents,
          failedDocuments: p.failed_documents,
          updatedAt: p.updated_at ?? p.updatedAt ?? null,
        }));

        mapped.sort((a, b) => {
          if (a.createdAt && b.createdAt) {
            return new Date(b.createdAt) - new Date(a.createdAt);
          }
          const aid = typeof a.id === 'number' ? a.id : 0;
          const bid = typeof b.id === 'number' ? b.id : 0;
          return bid - aid;
        });

        setProjects(mapped);

        const map = {};
        mapped.forEach((p) => {
          if (p.name != null && p.id != null) {
            map[p.name] = p.id;
          }
        });
        sessionStorage.setItem("projects_map", JSON.stringify(map));
      } catch (e) {
        console.error("Failed to load projects", e);
      }
    };

    fetchProjects();
  }, []);

  const handleCreateProject = (newProject) => {
    setProjects((prev) => [newProject, ...prev]);
    setSelectedProject(newProject);
    // Immediately resolve and set backend project id so Dashboard fetches correct data
    const newProjectId = getProjectIdByName(newProject.name);
    setSelectedProjectId(newProjectId);
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
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden"
       }}>
        {/* Sidebar */}
        <Sidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          selectedProject={selectedProject}
          onProjectSelect={handleProjectSelect}
          onCreateProject={handleCreateProjectOpen}
          isMobile={isMobile}
          projects={projects}
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
            selectedProjectId={selectedProjectId}
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
