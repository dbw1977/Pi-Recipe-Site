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

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Library /> },
      { path: 'new', element: <RecipeEdit /> },
      { path: 'import', element: <Import /> },
      { path: 'drafts', element: <Drafts /> },
      { path: 'recipe/:id', element: <RecipeView /> },
      { path: 'recipe/:id/edit', element: <RecipeEdit /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
