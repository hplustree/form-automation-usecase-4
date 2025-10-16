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
// import { projects } from "../data/mockData";
import FolderIcon from "@mui/icons-material/Folder";
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined';
const DRAWER_WIDTH = 319;

const Sidebar = ({
  open,
  onClose,
  selectedProject,
  onProjectSelect,
  onCreateProject,
  isMobile,
  projects
}) => {
  const theme = useTheme();

  const drawerContent = (
    <Box
      sx={{
        // width: DRAWER_WIDTH,
        height: "100%",
        // backgroundColor:"#E3E5E880",
        backgroundColor: theme.palette.mode === 'light' ? "#F5F6F7" : "#202124",
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

      <List 
      // sx={{ px: 1 }}
      sx={{margin:0 , padding:0}}
      >
        {projects && projects.length > 0  ? ( 
          
        projects.map((project) => (
        <ListItem
          key={project.id}
          button
          onClick={() => onProjectSelect(project)}
          sx={{
            borderRadius: "6px",
            py: 0.4,
            px: 0.5,
            mb: 0.2,
            display: "flex",
            alignItems: "center",
            backgroundColor:
              selectedProject?.id === project.id
                ? (theme.palette.mode === "dark" ? "#1b1c1f" : "#E3E5E8")
                : "transparent",
            "&:hover": {
              backgroundColor: selectedProject?.id === project.id
                ? (theme.palette.mode === "dark" ? "#17181b" : "#DADDE1")
                : (theme.palette.mode === "dark" ? "rgba(255,255,255,0.04)" : "#E3E5E8"),
            },
            transition: "all 0.2s ease",
            cursor: "pointer",
          }}
        >
          <ListItemIcon
            sx={{
              minWidth: 28,
              color: theme.palette.mode === "dark" ? "white" : "#5f6368",
              mt: "1px",
            }}
          >
            <FolderOutlinedIcon fontSize="small" />
          </ListItemIcon>

          <Box sx={{ flex: 1 }}>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 500,
                // color: "#202124",
                color:theme.palette.mode === "dark" ? "white" : "#202124",
                fontSize: "0.88rem",
                lineHeight: 1.2,
              }}
            >
              {project.name}
            </Typography>
            <Typography
              variant="caption"
              sx={{
                color: "#5f6368",
                // color:theme.palette.mode === "dark" ? "white" : "#5f6368",
                fontSize: "0.73rem",
              }}
            >
              {project.documentCount} documents
            </Typography>
          </Box>

          <ListItemIcon sx={{ minWidth: 22 }}>
            {/* {selectedProject?.id === project.id ? ( */}
              {/* <ExpandMoreIcon fontSize="small" sx={{ color: "#5f6368" }} /> */}
            {/* ) : ( */}
              <ChevronRightIcon fontSize="small" sx={{ color: "#5f6368" }} />
            {/* )} */}
          </ListItemIcon>
        </ListItem>


        ))) :
         (
          <Typography
      variant="body2"
      color="text.secondary"
      sx={{
        textAlign: "center",
        mt: 2,
        fontStyle: "italic",
      }}
    >
      No projects available
        </Typography>
        )}
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
