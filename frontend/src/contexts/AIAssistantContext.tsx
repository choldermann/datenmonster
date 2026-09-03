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
  setPageContextActions: (actions: Record<string, PageAction>) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  setGenerateNodesCallback: (fn: ((result: any) => void) | null) => void;
  callGenerateNodes: (result: any) => void;
  setSuggestTablesCallback: (fn: ((result: any) => void) | null) => void;
  callSuggestTables: (result: any) => void;
  pendingMessage: string | null;
  setPendingMessage: (msg: string | null) => void;
  triggerExplainError: (errorText: string, extraContext?: Record<string, any>) => void;
  // Opt-in: Formular-Runner blenden den schwebenden Assistenten standardmäßig aus
  // (er wird dort nicht mit Formulardaten gefüttert). Ein Formular/Template kann
  // ihn per schema.show_ai_assistant wieder einblenden.
  formAiAllowed: boolean;
  setFormAiAllowed: (v: boolean) => void;
  // Einzelne Bereiche blenden den schwebenden Assistenten aus, weil sie ihn
  // selbst ersetzen – die KI-Werkbank ist derselbe Assistent, nur ganzseitig.
  // Zwei Einstiege nebeneinander sind kein Angebot, sondern eine Frage an den
  // Anwender, die er nicht beantworten kann.
  versteckt: boolean;
  setVersteckt: (v: boolean) => void;
}

const AIAssistantContext = createContext<AIAssistantContextType>({
  pageContext: null,
  setPageContext: () => {},
  setPageContextActions: () => {},
  isOpen: false,
  setIsOpen: () => {},
  setGenerateNodesCallback: () => {},
  callGenerateNodes: () => {},
  setSuggestTablesCallback: () => {},
  callSuggestTables: () => {},
  pendingMessage: null,
  setPendingMessage: () => {},
  triggerExplainError: () => {},
  formAiAllowed: false,
  setFormAiAllowed: () => {},
  versteckt: false,
  setVersteckt: () => {},
});

export function AIAssistantProvider({ children }: { children: ReactNode }) {
  const [pageContext, _setPageContext] = useState<PageContext | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [formAiAllowed, setFormAiAllowed] = useState(false);
  const [versteckt, setVersteckt] = useState(false);
  const generateNodesCallbackRef = useRef<((result: any) => void) | null>(null);
  const suggestTablesCallbackRef = useRef<((result: any) => void) | null>(null);

  const setPageContext = useCallback((ctx: PageContext | null) => {
    _setPageContext(ctx);
  }, []);

  const setPageContextActions = useCallback((actions: Record<string, PageAction>) => {
    _setPageContext(prev => prev ? { ...prev, actions } : prev);
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

  const triggerExplainError = useCallback((errorText: string, extraContext?: Record<string, any>) => {
    _setPageContext(prev => prev ? {
      ...prev,
      currentData: { ...(prev.currentData ?? {}), lastRunError: { message: errorText, ...extraContext } },
    } : prev);
    setPendingMessage(`Analysiere diesen Mapping-Fehler und erkläre was schiefgelaufen ist und wie man es behebt:\n\n${errorText}`);
    setIsOpen(true);
  }, []);

  return (
    <AIAssistantContext.Provider value={{ pageContext, setPageContext, setPageContextActions, isOpen, setIsOpen, setGenerateNodesCallback, callGenerateNodes, setSuggestTablesCallback, callSuggestTables, pendingMessage, setPendingMessage, triggerExplainError, formAiAllowed, setFormAiAllowed, versteckt, setVersteckt }}>
      {children}
    </AIAssistantContext.Provider>
  );
}

export function useAIAssistant() {
  return useContext(AIAssistantContext);
}
