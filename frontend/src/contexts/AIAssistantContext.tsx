import { createContext, useContext, useState, useCallback, useRef, ReactNode } from "react";

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
  setGenerateNodesCallback: (fn: ((result: any) => void) | null) => void;
  callGenerateNodes: (result: any) => void;
  setSuggestTablesCallback: (fn: ((result: any) => void) | null) => void;
  callSuggestTables: (result: any) => void;
}

const AIAssistantContext = createContext<AIAssistantContextType>({
  pageContext: null,
  setPageContext: () => {},
  isOpen: false,
  setIsOpen: () => {},
  setGenerateNodesCallback: () => {},
  callGenerateNodes: () => {},
  setSuggestTablesCallback: () => {},
  callSuggestTables: () => {},
});

export function AIAssistantProvider({ children }: { children: ReactNode }) {
  const [pageContext, _setPageContext] = useState<PageContext | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const generateNodesCallbackRef = useRef<((result: any) => void) | null>(null);
  const suggestTablesCallbackRef = useRef<((result: any) => void) | null>(null);

  const setPageContext = useCallback((ctx: PageContext | null) => {
    _setPageContext(ctx);
  }, []);

  const setGenerateNodesCallback = useCallback((fn: ((result: any) => void) | null) => {
    generateNodesCallbackRef.current = fn;
  }, []);

  const callGenerateNodes = useCallback((result: any) => {
    generateNodesCallbackRef.current?.(result);
  }, []);

  const setSuggestTablesCallback = useCallback((fn: ((result: any) => void) | null) => {
    suggestTablesCallbackRef.current = fn;
  }, []);

  const callSuggestTables = useCallback((result: any) => {
    suggestTablesCallbackRef.current?.(result);
  }, []);

  return (
    <AIAssistantContext.Provider value={{ pageContext, setPageContext, isOpen, setIsOpen, setGenerateNodesCallback, callGenerateNodes, setSuggestTablesCallback, callSuggestTables }}>
      {children}
    </AIAssistantContext.Provider>
  );
}

export function useAIAssistant() {
  return useContext(AIAssistantContext);
}
