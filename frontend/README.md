# Judex React Frontend

Modern, scalable React frontend for Judex video analysis platform.

## 🏗️ Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **React Router** - Navigation
- **Zustand** - State management
- **React Query** - Data fetching
- **Axios** - HTTP client
- **Lucide React** - Icons
- **React Hot Toast** - Notifications

## 📁 Project Structure

```
frontend/
├── public/                    # Static assets
├── src/
│   ├── api/                   # API client and endpoints
│   │   ├── client.ts          # Axios instance
│   │   ├── endpoints/
│   │   │   ├── videos.ts      # Video endpoints
│   │   │   ├── live.ts        # Live feed endpoints
│   │   │   ├── analytics.ts   # Analytics endpoints
│   │   │   └── settings.ts    # Settings endpoints
│   │   └── types.ts           # API response types
│   ├── components/
│   │   ├── common/            # Reusable components
│   │   │   ├── Button.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Spinner.tsx
│   │   │   └── VideoPlayer.tsx
│   │   ├── layout/            # Layout components
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── Layout.tsx
│   │   ├── pipeline/          # Pipeline tab components
│   │   │   ├── FileTree.tsx
│   │   │   ├── PipelineView.tsx
│   │   │   ├── StageProgress.tsx
│   │   │   └── ResultsPanel.tsx
│   │   ├── liveFeed/          # Live feed components
│   │   │   ├── StreamConfig.tsx
│   │   │   ├── LivePreview.tsx
│   │   │   ├── DetectionCanvas.tsx
│   │   │   └── RecentEvents.tsx
│   │   ├── liveEvents/        # Live events components
│   │   │   ├── EventsTable.tsx
│   │   │   ├── EventViewer.tsx
│   │   │   └── EventFilters.tsx
│   │   ├── analytics/         # Analytics components
│   │   │   ├── StatsCards.tsx
│   │   │   ├── ViolationChart.tsx
│   │   │   └── ModelMetrics.tsx
│   │   └── settings/          # Settings components
│   │       ├── PolicyConfig.tsx
│   │       └── ThresholdSlider.tsx
│   ├── hooks/                 # Custom hooks
│   │   ├── useVideoProcessing.ts
│   │   ├── useLiveFeed.ts
│   │   ├── useSSE.ts
│   │   └── useFileUpload.ts
│   ├── pages/                 # Page components
│   │   ├── Pipeline.tsx
│   │   ├── LiveFeed.tsx
│   │   ├── LiveEvents.tsx
│   │   ├── Analytics.tsx
│   │   └── Settings.tsx
│   ├── store/                 # Zustand stores
│   │   ├── videoStore.ts
│   │   ├── liveStore.ts
│   │   └── settingsStore.ts
│   ├── types/                 # TypeScript types
│   │   ├── video.ts
│   │   ├── live.ts
│   │   └── common.ts
│   ├── utils/                 # Utility functions
│   │   ├── formatters.ts
│   │   ├── validators.ts
│   │   └── helpers.ts
│   ├── App.tsx                # Root component
│   ├── main.tsx               # Entry point
│   └── index.css              # Global styles
├── .env.example               # Environment variables template
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 🚀 Getting Started

### Install Dependencies

```bash
npm install
```

### Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
VITE_API_URL=http://localhost:8012
VITE_WS_URL=ws://localhost:8012
```

### Run Development Server

```bash
npm run dev
```

Access at `http://localhost:5173`

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## 🎨 Component Guidelines

### Component Structure

```tsx
// components/example/MyComponent.tsx
import { FC } from 'react';
import { MyComponentProps } from './types';

export const MyComponent: FC<MyComponentProps> = ({ prop1, prop2 }) => {
  return (
    <div className="my-component">
      {/* Component content */}
    </div>
  );
};
```

### Custom Hooks

```tsx
// hooks/useExample.ts
import { useState, useEffect } from 'react';

export const useExample = () => {
  const [data, setData] = useState(null);
  
  useEffect(() => {
    // Logic here
  }, []);
  
  return { data };
};
```

### State Management (Zustand)

```tsx
// store/exampleStore.ts
import { create } from 'zustand';

interface ExampleStore {
  value: string;
  setValue: (value: string) => void;
}

export const useExampleStore = create<ExampleStore>((set) => ({
  value: '',
  setValue: (value) => set({ value }),
}));
```

## 📡 API Integration

### Using React Query

```tsx
import { useQuery } from '@tanstack/react-query';
import { videoApi } from '@/api/endpoints/videos';

const { data, isLoading, error } = useQuery({
  queryKey: ['videos'],
  queryFn: videoApi.getAll,
});
```

### SSE Connection

```tsx
import { useSSE } from '@/hooks/useSSE';

const { data, connect, disconnect } = useSSE('/sse/video-123');
```

## 🎯 Key Features

### 1. Pipeline Tab
- File tree for video management
- Real-time processing progress
- Interactive pipeline stages
- Results visualization

### 2. Live Feed
- Multiple stream sources (Webcam, RTSP, RTMP, HTTP)
- Real-time detection overlay
- Event notifications
- Performance metrics

### 3. Live Events
- Event history table
- Filtering and search
- Event details viewer
- Manual review interface

### 4. Analytics
- Aggregate statistics
- Violation trends
- Model performance metrics
- Export capabilities

### 5. Settings
- Policy configuration
- Threshold management
- Preset selection
- System preferences

## 🔧 Configuration

### Vite Config

Already configured with:
- React plugin
- TypeScript support
- Path aliases (@/ for src/)
- Proxy for API requests

### TypeScript Config

Strict mode enabled with:
- ES2022 target
- JSX support
- Path mapping
- Type checking

## 📦 Scripts

```json
{
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
  "type-check": "tsc --noEmit"
}
```

## 🎨 Styling Guidelines

### TailwindCSS Classes

Use utility-first approach:
```tsx
<div className="flex items-center justify-between p-4 bg-white rounded-lg shadow-md">
  <h2 className="text-xl font-bold text-gray-900">Title</h2>
</div>
```

### Custom Colors

Defined in `tailwind.config.js`:
- `primary` - Main brand color
- `secondary` - Secondary accent
- `success`, `warning`, `danger` - Status colors
- `dark-*` - Dark theme variants

## 🔒 Type Safety

All components are fully typed:
- Props interfaces
- API responses
- Store state
- Event handlers

## 🧪 Testing (Future)

Structure ready for:
- Vitest for unit tests
- React Testing Library
- Playwright for E2E

## 📱 Responsive Design

Mobile-first approach:
- Tailwind breakpoints
- Adaptive layouts
- Touch-friendly interfaces

## ⚡ Performance

Optimizations:
- Code splitting
- Lazy loading
- React Query caching
- Memoization

## 🚀 Deployment

### Docker

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
```

### Environment Variables

Production:
```env
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com
```

## 📝 Notes

- All components match the original UI functionality
- Maintains the same API contract
- Improved code organization
- Better maintainability
- Easier to extend and test
- Type-safe throughout

## 🤝 Contributing

1. Follow component structure
2. Use TypeScript strictly
3. Write descriptive commit messages
4. Test before submitting

---

**Ready to scale!** 🚀
