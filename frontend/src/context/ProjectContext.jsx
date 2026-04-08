import { createContext, useContext, useState, useEffect } from "react";

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [activeProject, setActiveProjectState] = useState(() => {
    try { return JSON.parse(localStorage.getItem("dm_active_project")) || null; }
    catch { return null; }
  });

  const setActiveProject = (project) => {
    setActiveProjectState(project);
    if (project) localStorage.setItem("dm_active_project", JSON.stringify(project));
    else localStorage.removeItem("dm_active_project");
  };

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
