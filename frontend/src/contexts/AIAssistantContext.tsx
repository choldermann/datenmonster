import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export interface PageAction {
  label: string;
  description: string;
  handler: () => void;
}

export interface PageContext {
  page: string;
  title: string;
  description?: string;
  currentData?: Record<string, unknown>;
  actions?: Record<string, PageAction>;
}

interface AIAssistantContextType {
  pageContext: PageContext | null;
  setPageContext: (ctx: PageContext | null) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

const AIAssistantContext = createContext<AIAssistantContextType>({
  pageContext: null,
  setPageContext: () => {},
  isOpen: false,
  setIsOpen: () => {},
});

export function AIAssistantProvider({ children }: { children: ReactNode }) {
  const [pageContext, _setPageContext] = useState<PageContext | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const setPageContext = useCallback((ctx: PageContext | null) => {
    _setPageContext(ctx);
  }, []);

  return (
    <AIAssistantContext.Provider value={{ pageContext, setPageContext, isOpen, setIsOpen }}>
      {children}
    </AIAssistantContext.Provider>
  );
}

export function useAIAssistant() {
  return useContext(AIAssistantContext);
}
