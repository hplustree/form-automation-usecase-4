import React from "react";
import {
  Drawer,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Typography,
  Button,
  Box,
  Divider,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import {
  Add as AddIcon,
  FolderOpen as FolderOpenIcon,
  ExpandMore as ExpandMoreIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import { projects } from "../data/mockData";
import FolderIcon from "@mui/icons-material/Folder";
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined';
const DRAWER_WIDTH = 280;

const Sidebar = ({
  open,
  onClose,
  selectedProject,
  onProjectSelect,
  onCreateProject,
  isMobile,
}) => {
  const theme = useTheme();

  const drawerContent = (
    <Box
      sx={{
        width: DRAWER_WIDTH,
        height: "100%",
        // marginTop: 0,
      }}
    >
      {/* Create New Project Button */}
      <Box sx={{ p: 2 }}>
        <Button
          variant="contained"
          fullWidth
          startIcon={<AddIcon />}
          onClick={onCreateProject}
          sx={{
            backgroundColor: "primary.main",
            "&:hover": {
              backgroundColor: "primary.dark",
            },
            textTransform: "none",
            fontWeight: 500,
            display: "flex",
            justifyContent: "flex-start",
            // py: 1.5,
          }}
        >
          Create New Project
        </Button>
      </Box>

      {/* <Divider /> */}

      {/* Projects Section */}
      <Box sx={{ p: 2, pb: 1 }}>
        <Typography
          variant="subtitle2"
          color="text.secondary"
          sx={{ fontWeight: 600 }}
        >
          Projects
        </Typography>
      </Box>

      <List sx={{ px: 1 }}>
        {projects.map((project) => (
          <ListItem
            key={project.id}
            button
            onClick={() => onProjectSelect(project)}
            sx={{
              borderRadius: 1,
              mb: 0.5,
              backgroundColor:
                selectedProject?.id === project.id ? "action.selected" : "transparent",
              "&:hover": {
                backgroundColor:
                  selectedProject?.id === project.id ? "action.selected" : "action.hover",
              },
            }}
          >
            <ListItemIcon sx={{ minWidth: 32, color: "text.primary" }}>
              <FolderOutlinedIcon />
            </ListItemIcon>
            <Box sx={{ flex: 1 }}>
              <ListItemText
                primary={
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 500, color: "text.primary" }}
                  >
                    {project.name}
                  </Typography>
                }
                secondary={
                  <Typography variant="caption" color="text.secondary">
                    {project.documentCount} documents
                  </Typography>
                }
              />
            </Box>
            <ListItemIcon sx={{ minWidth: 32 }}>
              {selectedProject?.id === project.id ? (
                <ExpandMoreIcon fontSize="small" />
              ) : (
                <ChevronRightIcon fontSize="small" />
              )}
            </ListItemIcon>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  if (isMobile) {
    return (
      <Drawer
        variant="temporary"
        open={open}
        onClose={onClose}
        ModalProps={{
          keepMounted: true, 
        }}
        sx={{
          "& .MuiDrawer-paper": {
            boxSizing: "border-box",
            width: DRAWER_WIDTH,
          },
        }}
      >
        {drawerContent}
      </Drawer>
    );
  }

  return (
    <Drawer
      variant="persistent"
      open={open}
      sx={{
        width: open ? DRAWER_WIDTH : 0,
        flexShrink: 0,
        transition: theme.transitions.create("width", {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.enteringScreen,
        }),
        "& .MuiDrawer-paper": {
          width: DRAWER_WIDTH,
          boxSizing: "border-box",
          position: "fixed",
          // top: (t) => t.mixins.toolbar.minHeight,
          // height: (t) => `calc(100% - ${t.mixins.toolbar.minHeight}px)`,
          transition: theme.transitions.create("transform", {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
          }),
          transform: open ? "translateX(0)" : `translateX(-${DRAWER_WIDTH}px)`,
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
};

export default Sidebar;
