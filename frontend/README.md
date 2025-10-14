# SiSo - Document Processing Interface

A modern, responsive React application for document processing and data extraction, built with Material-UI and designed for optimal user experience across all devices.

## 🎯 Features

### ✨ Complete UI Implementation
- **Modern Design**: Clean, professional interface matching the provided screenshots
- **Responsive Layout**: Fully optimized for desktop, tablet, and mobile devices
- **Material-UI Components**: Consistent design system with custom theming

### 📋 Project Management
- **Project Sidebar**: Easy navigation between different projects
- **Create New Project**: Modal interface for creating projects with:
  - Project name configuration
  - Document upload (drag & drop support)
  - Key points selection (Entity Information, Financial Data, Contact Information)

### 📊 Document Processing Dashboard
- **Processing Queue**: Real-time status tracking with progress indicators
- **Extraction Results**: Tabbed interface showing processed document data
- **Interactive Tables**: Click-to-edit functionality (ready for API integration)

### 📱 Mobile-First Design
- **Responsive Sidebar**: Collapsible navigation for mobile devices
- **Touch-Friendly**: Optimized button sizes and spacing
- **Progressive Enhancement**: Features scale gracefully across screen sizes

## 🚀 Technology Stack

- **React 18** - Modern functional components with hooks
- **Vite** - Fast development server and build tool
- **Material-UI v5** - Complete component library and theming system
- **JavaScript (JSX)** - No TypeScript for easier maintenance
- **CSS-in-JS** - Styled components with sx prop

## 📦 Installation & Setup

### Prerequisites
- Node.js (version 16 or higher)
- npm or yarn package manager

### Quick Start
```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

### Available Scripts
- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## 🗂️ Project Structure

```
src/
├── components/           # Reusable UI components
│   ├── Header.jsx       # Application header with mobile menu
│   ├── Sidebar.jsx      # Project navigation sidebar
│   ├── Dashboard.jsx    # Main content area with tabs
│   └── CreateProjectModal.jsx  # Project creation modal
├── data/
│   └── mockData.js      # Static data (easily replaceable with API)
├── theme/
│   └── theme.js         # Material-UI theme configuration
├── App.jsx              # Main application component
└── main.jsx            # Application entry point
```

## 🔧 Key Components

### Header Component
- Fixed navigation bar with SiSo branding
- Mobile hamburger menu integration
- Theme toggle button (ready for implementation)

### Sidebar Component
- Project list with document counts
- Create new project button
- Responsive drawer behavior (permanent on desktop, temporary on mobile)

### Dashboard Component
- Tabbed interface (Results/Processing)
- Processing queue with real-time status
- Data extraction results table
- Mobile-optimized table with responsive column hiding

### CreateProjectModal Component
- Form validation and state management
- Drag & drop file upload area
- Checkbox groups for key point selection
- Mobile-friendly full-screen modal on small devices

## 📊 Data Structure

### Projects
```javascript
{
  id: 1,
  name: 'Q1 2024 Invoices',
  documentCount: 12,
  isActive: true,
  type: 'invoice'
}
```

### Processing Queue
```javascript
{
  id: 1,
  fileName: 'invoice_2024_001.pdf',
  status: 'completed', // 'pending', 'processing', 'completed'
  progress: 100
}
```

### Extraction Results
```javascript
{
  id: 1,
  fileName: 'invoice_2024_001.pdf',
  company: 'Acme Corporation',
  date: '2024-01-15',
  amount: '$5,240.00',
  invoice: 'INV-2024-001'
}
```

## 🔌 API Integration Ready

The application is structured for easy API integration:

### Replace Mock Data
1. Update `src/data/mockData.js` with API endpoints
2. Implement async/await patterns in components
3. Add loading states and error handling

### Example API Integration
```javascript
// In your component
const [projects, setProjects] = useState([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  const fetchProjects = async () => {
    try {
      const response = await fetch('/api/projects');
      const data = await response.json();
      setProjects(data);
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    } finally {
      setLoading(false);
    }
  };
  
  fetchProjects();
}, []);
```

## 📱 Responsive Design Features

### Breakpoints
- **Mobile**: < 600px (xs)
- **Tablet**: 600px - 960px (sm)
- **Desktop**: > 960px (md+)

### Mobile Optimizations
- Collapsible sidebar with overlay
- Full-screen modals on mobile
- Responsive table with column hiding
- Touch-friendly button sizes
- Optimized spacing and typography

### Desktop Enhancements
- Permanent sidebar navigation
- Hover effects and transitions
- Multi-column layouts
- Enhanced data density

## 🎨 Theming & Customization

### Custom Theme
- Primary color: #1976d2 (Material Design Blue)
- Custom typography with Inter font family
- Consistent spacing and border radius
- Enhanced component styles (Cards, Buttons, Tables)

## 🚧 Future API Endpoints

```
GET    /api/projects              # List all projects
POST   /api/projects              # Create new project
GET    /api/projects/:id/queue    # Get processing queue
GET    /api/projects/:id/results  # Get extraction results
POST   /api/projects/:id/upload   # Upload documents
```

**Built with ❤️ using React, Material-UI, and modern web technologies.**
