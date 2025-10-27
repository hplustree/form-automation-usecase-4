import React, { createContext, useContext, useState, useEffect } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';

const ThemeContext = createContext();

export const useThemeMode = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useThemeMode must be used within a ThemeProvider');
  }
  return context;
};

const getTheme = (mode) => createTheme({
  palette: {
    mode,
    primary: {
      main: '#2662D9',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: mode === 'light' ? '#f5f5f5' : '#121212',
      paper: mode === 'light' ? '#ffffff' : '#1e1e1e',
    },
    text: {
      primary: mode === 'light' ? 'rgba(0, 0, 0, 0.87)' : 'rgba(255, 255, 255, 0.87)',
      secondary: mode === 'light' ? 'rgba(0, 0, 0, 0.6)' : 'rgba(255, 255, 255, 0.6)',
    },
    success: {
      main: '#21C45D', 
      light: '#21C45D1A', 
      dark: '#388e3c',
    },
    warning: {
      main: '#ff9800',
      light: '#F59F0A1A',
      dark: '#f57c00',
    },
    info: {
      main: '#2196f3',
      light: '#64b5f6',
      dark: '#1976d2',
    },
    divider: mode === 'light' ? 'rgba(0, 0, 0, 0.12)' : 'rgba(255, 255, 255, 0.12)',
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
    body1: {
      fontSize: '0.95rem',
    },
    body2: {
      fontSize: '0.875rem',
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: mode === 'light' 
            ? '0 2px 8px rgba(0, 0, 0, 0.1)' 
            : '0 2px 8px rgba(0, 0, 0, 0.3)',
          transition: 'box-shadow 0.2s ease-in-out, transform 0.1s ease-in-out',
          '&:hover': {
            boxShadow: mode === 'light' 
              ? '0 4px 12px rgba(0, 0, 0, 0.15)' 
              : '0 4px 12px rgba(0, 0, 0, 0.4)',
            transform: 'translateY(-1px)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          borderRadius: 8,
        },
        contained: {
          boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
          '&:hover': {
            boxShadow: '0 4px 8px rgba(0, 0, 0, 0.15)',
            transform: 'translateY(-1px)',
          },
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          backgroundColor: mode === 'light' ? '#f8f9fa' : '#2a2a2a',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          color: mode === 'light' ? 'rgba(0,0,0,0.87)' : 'rgba(255,255,255,0.87)'
        },
      }
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: mode === 'light' ? '#fafafa' : '#1a1a1a',
          borderRight: mode === 'light' 
            ? '1px solid rgba(0, 0, 0, 0.12)' 
            : '1px solid rgba(255, 255, 255, 0.12)',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: mode === 'light' ? '#ffffff' : '#1e1e1e',
          color: mode === 'light' ? '#000000' : '#ffffff',
          boxShadow: mode === 'light' 
            ? '0 1px 3px rgba(0,0,0,0.1)' 
            : '0 1px 3px rgba(255,255,255,0.1)',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 16,
        },
        colorSuccess: {
          backgroundColor: mode === 'light' ? '#e8f5e8' : '#2d5a2d',
          color: mode === 'light' ? '#2e7d32' : '#81c784',
          '& .MuiChip-icon': {
            color: mode === 'light' ? '#2e7d32' : '#81c784',
          },
        },
        colorWarning: {
          backgroundColor: mode === 'light' ? '#fff3e0' : '#5d4037',
          color: mode === 'light' ? '#ef6c00' : '#ffb74d',
        },
      },
    },
  },
});

export const CustomThemeProvider = ({ children }) => {
  const [mode, setMode] = useState(() => {
    const savedMode = sessionStorage.getItem('themeMode');
    return savedMode || 'light';
  });

  const theme = getTheme(mode);

  const toggleTheme = () => {
    const newMode = mode === 'light' ? 'dark' : 'light';
    setMode(newMode);
    sessionStorage.setItem('themeMode', newMode);
  };

  const value = {
    mode,
    toggleTheme,
    theme,
  };

  return (
    <ThemeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        {children}
      </ThemeProvider>
    </ThemeContext.Provider>
  );
};