import React from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  Box,
  IconButton,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import {
  Menu as MenuIcon,
  LightMode as LightModeIcon,
  DarkMode as DarkModeIcon,
} from "@mui/icons-material";
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import { useThemeMode } from "../context/ThemeContext";

function Header({ onMenuClick, sidebarOpen, isMobile, drawerWidth = 282 }) {
  const theme = useTheme();
  const { mode, toggleTheme } = useThemeMode();

  return (
    <AppBar
      position="fixed"
      elevation={1}
      sx={{
        zIndex: (t) => t.zIndex.drawer + 1,
        left: !isMobile && sidebarOpen ? `${drawerWidth}px` : 0,
        width:
          !isMobile && sidebarOpen ? `calc(100% - ${drawerWidth}px)` : "100%",
        transition: theme.transitions.create(["width", "left"], {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.leavingScreen,
        }),
      }}
    >
      <Toolbar sx={{ justifyContent: "space-between" }}>
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              bgcolor: "primary.main",
              color: "primary.contrastText",
              px: 1,
              py: 1,
              borderRadius: 0.8,
              mr: 2,
            }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path>
              <path d="M14 2v4a2 2 0 0 0 2 2h4"></path>
              <path d="M10 9H8"></path>
              <path d="M16 13H8"></path>
              <path d="M16 17H8"></path>
            </svg>
          </Box>

          <Box>
            <Typography
              variant="body1"
              color="text.primary"
              sx={{ fontWeight: 600, fontSize: "1.2rem" }}
            >
              SiSo
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ fontWeight: 400, fontSize: "0.8rem" }}>
              Document Processing 
            </Typography>
          </Box>
        </Box>

        {/* Right Side: Dark/Light Mode Icon commented as not required now */}
        {/* <Box>
          <IconButton
            color="inherit"
            onClick={toggleTheme}
            sx={{
              transition: "transform 0.2s ease-in-out",
              "&:hover": {
                transform: "scale(1.1)",
              },
            }}
          >
            {mode === "light" ? <DarkModeOutlinedIcon /> : <LightModeOutlinedIcon />}
            
          </IconButton>
        </Box> */}
      </Toolbar>
    </AppBar>
  );
}

export default Header;
