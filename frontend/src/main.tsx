import React from 'react';
import ReactDOM from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import './index.css';
import App from './App';
import Library from './pages/Library';
import RecipeView from './pages/RecipeView';
import RecipeEdit from './pages/RecipeEdit';
import Import from './pages/Import';
import Drafts from './pages/Drafts';
import Settings from './pages/Settings';
import PlacesLibrary from './pages/PlacesLibrary';
import PlaceView from './pages/PlaceView';
import PlaceEdit from './pages/PlaceEdit';
import PlaceImport from './pages/PlaceImport';
import PlaceDrafts from './pages/PlaceDrafts';
import PlacesExport from './pages/PlacesExport';

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      // Cook (recipes)
      { index: true, element: <Library /> },
      { path: 'new', element: <RecipeEdit /> },
      { path: 'import', element: <Import /> },
      { path: 'drafts', element: <Drafts /> },
      { path: 'settings', element: <Settings /> },
      { path: 'recipe/:id', element: <RecipeView /> },
      { path: 'recipe/:id/edit', element: <RecipeEdit /> },
      // Eat Out (places)
      { path: 'eat', element: <PlacesLibrary /> },
      { path: 'eat/new', element: <PlaceEdit /> },
      { path: 'eat/import', element: <PlaceImport /> },
      { path: 'eat/drafts', element: <PlaceDrafts /> },
      { path: 'eat/export', element: <PlacesExport /> },
      { path: 'eat/place/:id', element: <PlaceView /> },
      { path: 'eat/place/:id/edit', element: <PlaceEdit /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
