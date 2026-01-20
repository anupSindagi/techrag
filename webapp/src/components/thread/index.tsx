import { v4 as uuidv4 } from "uuid";
import { ReactNode, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useStreamContext } from "@/providers/Stream";
import { useState, FormEvent } from "react";
import { Button } from "../ui/button";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import { AssistantMessage, AssistantMessageLoading } from "./messages/ai";
import { HumanMessage } from "./messages/human";
import {
  DO_NOT_RENDER_ID_PREFIX,
  ensureToolCallsHaveResponses,
} from "@/lib/ensure-tool-responses";
import { TooltipIconButton } from "./tooltip-icon-button";
import {
  ArrowDown,
  LoaderCircle,
  PanelRightOpen,
  PanelRightClose,
  SquarePen,
  XIcon,
} from "lucide-react";
import { useQueryState, parseAsBoolean } from "nuqs";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import ThreadHistory from "./history";
import { toast } from "sonner";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { useFileUpload } from "@/hooks/use-file-upload";
import { ContentBlocksPreview } from "./ContentBlocksPreview";
import {
  useArtifactOpen,
  ArtifactContent,
  ArtifactTitle,
  useArtifactContext,
} from "./artifact";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../ui/sheet";
import dynamic from "next/dynamic";

// Dynamically import GraphVisualization with SSR disabled (uses browser-only APIs)
const GraphVisualization = dynamic(
  () =>
    import("@/components/graph/GraphVisualization").then(
      (mod) => mod.GraphVisualization
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[400px] items-center justify-center rounded-lg border border-gray-200 bg-gray-50">
        <div className="text-gray-500">Loading graph...</div>
      </div>
    ),
  }
);

function StickyToBottomContent(props: {
  content: ReactNode;
  footer?: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const context = useStickToBottomContext();
  return (
    <div
      ref={context.scrollRef}
      style={{ width: "100%", height: "100%" }}
      className={props.className}
    >
      <div
        ref={context.contentRef}
        className={props.contentClassName}
      >
        {props.content}
      </div>

      {props.footer}
    </div>
  );
}

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="h-4 w-4" />
      <span>Scroll to bottom</span>
    </Button>
  );
}

export function Thread() {
  const [artifactContext, setArtifactContext] = useArtifactContext();
  const [artifactOpen, closeArtifact] = useArtifactOpen();

  const [threadId, _setThreadId] = useQueryState("threadId");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [hideToolCalls, setHideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );
  const [input, setInput] = useState("");
  const {
    contentBlocks,
    setContentBlocks,
    handleFileUpload: _handleFileUpload,
    dropRef,
    removeBlock,
    resetBlocks: _resetBlocks,
    dragOver,
    handlePaste,
  } = useFileUpload();
  const [firstTokenReceived, setFirstTokenReceived] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");

  const stream = useStreamContext();
  const messages = stream.messages;
  const isLoading = stream.isLoading;

  const lastError = useRef<string | undefined>(undefined);

  const setThreadId = (id: string | null) => {
    _setThreadId(id);

    // close artifact and reset artifact context
    closeArtifact();
    setArtifactContext({});
  };

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      return;
    }
    try {
      const message = (stream.error as any).message;
      if (!message || lastError.current === message) {
        // Message has already been logged. do not modify ref, return early.
        return;
      }

      // Message is defined, and it has not been logged yet. Save it, and send the error
      lastError.current = message;
      toast.error("An error occurred. Please try again.", {
        description: (
          <p>
            <strong>Error:</strong> <code>{message}</code>
          </p>
        ),
        richColors: true,
        closeButton: true,
      });
    } catch {
      // no-op
    }
  }, [stream.error]);

  // TODO: this should be part of the useStream hook
  const prevMessageLength = useRef(0);
  useEffect(() => {
    if (
      messages.length !== prevMessageLength.current &&
      messages?.length &&
      messages[messages.length - 1].type === "ai"
    ) {
      setFirstTokenReceived(true);
    }

    prevMessageLength.current = messages.length;
  }, [messages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if ((input.trim().length === 0 && contentBlocks.length === 0) || isLoading)
      return;
    setFirstTokenReceived(false);

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [
        ...(input.trim().length > 0 ? [{ type: "text", text: input }] : []),
        ...contentBlocks,
      ] as Message["content"],
    };

    const toolMessages = ensureToolCallsHaveResponses(stream.messages);

    const context =
      Object.keys(artifactContext).length > 0 ? artifactContext : undefined;

    stream.submit(
      { messages: [...toolMessages, newHumanMessage], context },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      {
        streamMode: ["values"],
        streamSubgraphs: true,
        streamResumable: true,
        optimisticValues: (prev: Record<string, unknown>) => ({
          ...prev,
          context,
          messages: [
            ...((prev.messages as Message[]) ?? []),
            ...toolMessages,
            newHumanMessage,
          ],
        }),
      } as any,
    );

    setInput("");
    setContentBlocks([]);
  };

  const handleSuggestedPrompt = (prompt: string) => {
    if (isLoading) return;
    setFirstTokenReceived(false);

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [{ type: "text", text: prompt }] as Message["content"],
    };

    stream.submit(
      { messages: [newHumanMessage] },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      {
        streamMode: ["values"],
        streamSubgraphs: true,
        streamResumable: true,
        optimisticValues: (prev: Record<string, unknown>) => ({
          ...prev,
          messages: [...((prev.messages as Message[]) ?? []), newHumanMessage],
        }),
      } as any,
    );
  };

  const handleRegenerate = (
    parentCheckpoint: Checkpoint | null | undefined,
  ) => {
    // Do this so the loading state is correct
    prevMessageLength.current = prevMessageLength.current - 1;
    setFirstTokenReceived(false);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    stream.submit(undefined, {
      checkpoint: parentCheckpoint,
      streamMode: ["values"],
      streamSubgraphs: true,
      streamResumable: true,
    } as any);
  };

  const chatStarted = !!threadId || !!messages.length;
  const hasNoAIOrToolMessages = !messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden">
      <div className="relative hidden lg:flex">
        <motion.div
          className="absolute z-20 h-full overflow-hidden border-r bg-white"
          style={{ width: 300 }}
          animate={
            isLargeScreen
              ? { x: chatHistoryOpen ? 0 : -300 }
              : { x: chatHistoryOpen ? 0 : -300 }
          }
          initial={{ x: -300 }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          <div
            className="relative h-full"
            style={{ width: 300 }}
          >
            <ThreadHistory />
          </div>
        </motion.div>
      </div>

      <div
        className={cn(
          "grid w-full grid-cols-[1fr_0fr] transition-all duration-500",
          artifactOpen && "grid-cols-[3fr_2fr]",
        )}
      >
        <motion.div
          className={cn(
            "relative flex min-w-0 flex-1 flex-col overflow-hidden",
            !chatStarted && "grid-rows-[1fr]",
          )}
          layout={isLargeScreen}
          animate={{
            marginLeft: chatHistoryOpen ? (isLargeScreen ? 300 : 0) : 0,
            width: chatHistoryOpen
              ? isLargeScreen
                ? "calc(100% - 300px)"
                : "100%"
              : "100%",
          }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          {!chatStarted && (
            <div className="absolute top-0 left-0 z-10 flex w-full items-center justify-between gap-3 p-2 pl-2 sm:pl-4">
              <div>
                {(!chatHistoryOpen || !isLargeScreen) && (
                  <Button
                    className="hover:bg-gray-100"
                    variant="ghost"
                    size="sm"
                    onClick={() => setChatHistoryOpen((p) => !p)}
                  >
                    {chatHistoryOpen ? (
                      <PanelRightOpen className="size-4 sm:size-5" />
                    ) : (
                      <PanelRightClose className="size-4 sm:size-5" />
                    )}
                  </Button>
                )}
              </div>
            </div>
          )}
          {chatStarted && (
            <div className="relative z-10 flex items-center justify-between gap-2 p-2 sm:gap-3">
              <div className="relative flex items-center justify-start gap-2">
                <div className="absolute left-0 z-10">
                  {(!chatHistoryOpen || !isLargeScreen) && (
                    <Button
                      className="hover:bg-gray-100"
                      variant="ghost"
                      size="sm"
                      onClick={() => setChatHistoryOpen((p) => !p)}
                    >
                      {chatHistoryOpen ? (
                        <PanelRightOpen className="size-4 sm:size-5" />
                      ) : (
                        <PanelRightClose className="size-4 sm:size-5" />
                      )}
                    </Button>
                  )}
                </div>
                <motion.button
                  className="flex cursor-pointer items-center gap-2"
                  onClick={() => setThreadId(null)}
                  animate={{
                    marginLeft: !chatHistoryOpen ? 40 : 0,
                  }}
                  transition={{
                    type: "spring",
                    stiffness: 300,
                    damping: 30,
                  }}
                >
                  <span className="text-lg font-semibold tracking-tight sm:text-xl">
                    Mag7 Agent
                  </span>
                </motion.button>
              </div>

              <div className="flex items-center gap-2 sm:gap-4">
                <TooltipIconButton
                  size="default"
                  className="p-2 sm:p-4"
                  tooltip="New thread"
                  variant="ghost"
                  onClick={() => setThreadId(null)}
                >
                  <SquarePen className="size-4 sm:size-5" />
                </TooltipIconButton>
              </div>

              <div className="from-background to-background/0 absolute inset-x-0 top-full h-5 bg-gradient-to-b" />
            </div>
          )}

          <StickToBottom className="relative flex-1 overflow-hidden">
            <StickyToBottomContent
              className={cn(
                "absolute inset-0 overflow-y-scroll px-2 sm:px-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent",
                !chatStarted && "mt-[10vh] flex flex-col items-stretch sm:mt-[25vh]",
                chatStarted && "grid grid-rows-[1fr_auto]",
              )}
              contentClassName="pt-4 pb-8 max-w-3xl mx-auto flex flex-col gap-4 w-full sm:pt-8 sm:pb-16"
              content={
                <>
                  {messages
                    .filter((m) => !m.id?.startsWith(DO_NOT_RENDER_ID_PREFIX))
                    .map((message, index) =>
                      message.type === "human" ? (
                        <HumanMessage
                          key={message.id || `${message.type}-${index}`}
                          message={message}
                          isLoading={isLoading}
                        />
                      ) : (
                        <AssistantMessage
                          key={message.id || `${message.type}-${index}`}
                          message={message}
                          isLoading={isLoading}
                          handleRegenerate={handleRegenerate}
                        />
                      ),
                    )}
                  {/* Special rendering case where there are no AI/tool messages, but there is an interrupt.
                    We need to render it outside of the messages list, since there are no messages to render */}
                  {hasNoAIOrToolMessages && !!stream.interrupt && (
                    <AssistantMessage
                      key="interrupt-msg"
                      message={undefined}
                      isLoading={isLoading}
                      handleRegenerate={handleRegenerate}
                    />
                  )}
                  {isLoading && !firstTokenReceived && (
                    <AssistantMessageLoading />
                  )}
                </>
              }
              footer={
                <div className="sticky bottom-0 flex flex-col items-center gap-4 bg-white px-2 pb-4 sm:gap-8 sm:px-4 sm:pb-0">
                  {!chatStarted && (
                    <div className="flex w-full max-w-3xl flex-col items-center gap-4 sm:gap-6">
                      <div className="flex flex-col items-center gap-3 text-center sm:gap-4">
                        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
                          Mag7 Agent
                        </h1>
                        <p className="text-xs text-gray-600 sm:text-sm">
                          AI-powered analysis of SEC 10-K filings for the
                          Magnificent 7 companies: Apple, Microsoft, Alphabet,
                          Amazon, NVIDIA, Meta, and Tesla.
                        </p>
                        <ul className="hidden text-left text-xs text-gray-500 space-y-1 sm:block">
                          <li>
                            <span className="font-medium text-gray-700">Data:</span>{" "}
                            Latest SEC 10-K Annual Filings from all Mag7 companies
                          </li>
                          <li>
                            <span className="font-medium text-gray-700">Knowledge Graph:</span>{" "}
                            Neo4j-powered with ~1,500 nodes and ~10,000 relationships, ingested using Graphiti
                          </li>
                          <li>
                            <span className="font-medium text-gray-700">Agent:</span>{" "}
                            LangGraph agent with Graphiti hybrid graph search and node search tools
                          </li>
                        </ul>
                      </div>

                      {/* Suggested Prompts */}
                      <div className="flex w-full flex-col gap-2">
                        <p className="text-xs text-gray-400 text-center">Try asking:</p>
                        <div className="flex flex-col gap-2">
                          <button
                            onClick={() =>
                              handleSuggestedPrompt(
                                "Compare the cash on balance sheet between all the Magnificent 7 companies"
                              )
                            }
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-left text-xs text-gray-700 shadow-sm transition-all hover:border-indigo-400 hover:bg-gray-50 sm:px-4 sm:py-3 sm:text-sm"
                          >
                            Compare the cash on balance sheet between all the Magnificent 7 companies
                          </button>
                          <button
                            onClick={() =>
                              handleSuggestedPrompt(
                                "What are some major legal concerns faced by the Magnificent 7 companies?"
                              )
                            }
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-left text-xs text-gray-700 shadow-sm transition-all hover:border-indigo-400 hover:bg-gray-50 sm:px-4 sm:py-3 sm:text-sm"
                          >
                            What are some major legal concerns faced by the Magnificent 7 companies?
                          </button>
                        </div>
                      </div>

                      {/* Play with Knowledge Graph Section */}
                      <button
                        onClick={() => setShowGraph(true)}
                        className="group flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2.5 shadow-sm transition-all hover:border-indigo-400 hover:bg-gray-50 sm:px-4 sm:py-3"
                      >
                        <svg
                          className="h-4 w-4 text-indigo-500 sm:h-5 sm:w-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <circle cx="12" cy="12" r="3" />
                          <circle cx="4" cy="6" r="2" />
                          <circle cx="20" cy="6" r="2" />
                          <circle cx="4" cy="18" r="2" />
                          <circle cx="20" cy="18" r="2" />
                          <path d="M12 9V6M12 15v3M9.5 10.5L6 8M14.5 10.5L18 8M9.5 13.5L6 16M14.5 13.5L18 16" />
                        </svg>
                        <span className="text-xs font-medium text-gray-700 sm:text-sm">
                          Play with the Knowledge Graph
                        </span>
                      </button>

                      {/* Knowledge Graph Modal */}
                      <Sheet open={showGraph} onOpenChange={setShowGraph}>
                        <SheetContent
                          side="bottom"
                          className="h-[85vh] sm:max-w-full"
                        >
                          <SheetHeader>
                            <SheetTitle className="flex items-center gap-2">
                              <svg
                                className="h-5 w-5 text-indigo-500"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <circle cx="12" cy="12" r="3" />
                                <circle cx="4" cy="6" r="2" />
                                <circle cx="20" cy="6" r="2" />
                                <circle cx="4" cy="18" r="2" />
                                <circle cx="20" cy="18" r="2" />
                                <path d="M12 9V6M12 15v3M9.5 10.5L6 8M14.5 10.5L18 8M9.5 13.5L6 16M14.5 13.5L18 16" />
                              </svg>
                              Knowledge Graph Explorer
                            </SheetTitle>
                            <SheetDescription>
                              Explore the entity-relationship graph extracted from SEC 10-K filings. Limited to 100 random nodes for performance. Drag nodes to interact.
                            </SheetDescription>
                          </SheetHeader>
                          <div className="flex-1 overflow-hidden px-4 pb-4">
                            <GraphVisualization />
                          </div>
                        </SheetContent>
                      </Sheet>
                    </div>
                  )}

                  <ScrollToBottom className="animate-in fade-in-0 zoom-in-95 absolute bottom-full left-1/2 mb-4 -translate-x-1/2" />

                  <div
                    ref={dropRef}
                    className={cn(
                      "bg-muted relative z-10 mx-auto mb-4 w-full max-w-3xl rounded-2xl shadow-xs transition-all sm:mb-8",
                      dragOver
                        ? "border-primary border-2 border-dotted"
                        : "border border-solid",
                    )}
                  >
                    <form
                      onSubmit={handleSubmit}
                      className="mx-auto grid max-w-3xl grid-rows-[1fr_auto] gap-2"
                    >
                      <ContentBlocksPreview
                        blocks={contentBlocks}
                        onRemove={removeBlock}
                      />
                      <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onPaste={handlePaste}
                        onKeyDown={(e) => {
                          if (
                            e.key === "Enter" &&
                            !e.shiftKey &&
                            !e.metaKey &&
                            !e.nativeEvent.isComposing
                          ) {
                            e.preventDefault();
                            const el = e.target as HTMLElement | undefined;
                            const form = el?.closest("form");
                            form?.requestSubmit();
                          }
                        }}
                        placeholder="Type your message..."
                        className="field-sizing-content min-h-[44px] resize-none border-none bg-transparent p-3 pb-0 text-base shadow-none ring-0 outline-none focus:ring-0 focus:outline-none sm:p-3.5"
                      />

                      <div className="flex items-center gap-2 p-2 pt-3 sm:gap-6 sm:pt-4">
                        <div className="hidden sm:block">
                          <div className="flex items-center space-x-2">
                            <Switch
                              id="render-tool-calls"
                              checked={hideToolCalls ?? false}
                              onCheckedChange={setHideToolCalls}
                            />
                            <Label
                              htmlFor="render-tool-calls"
                              className="text-sm text-gray-600"
                            >
                              Hide Tool Calls
                            </Label>
                          </div>
                        </div>
                        {stream.isLoading ? (
                          <Button
                            key="stop"
                            onClick={() => stream.stop()}
                            className="ml-auto"
                          >
                            <LoaderCircle className="h-4 w-4 animate-spin" />
                            <span className="hidden sm:inline">Cancel</span>
                          </Button>
                        ) : (
                          <Button
                            type="submit"
                            className="ml-auto shadow-md transition-all"
                            disabled={
                              isLoading ||
                              (!input.trim() && contentBlocks.length === 0)
                            }
                          >
                            Send
                          </Button>
                        )}
                      </div>
                    </form>
                  </div>
                </div>
              }
            />
          </StickToBottom>
        </motion.div>
        <div className="relative flex flex-col border-l">
          <div className="absolute inset-0 flex min-w-[30vw] flex-col">
            <div className="grid grid-cols-[1fr_auto] border-b p-4">
              <ArtifactTitle className="truncate overflow-hidden" />
              <button
                onClick={closeArtifact}
                className="cursor-pointer"
              >
                <XIcon className="size-5" />
              </button>
            </div>
            <ArtifactContent className="relative flex-grow" />
          </div>
        </div>
      </div>
    </div>
  );
}
