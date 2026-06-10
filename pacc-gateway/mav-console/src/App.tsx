import React, { useState, useEffect, useRef } from 'react';
import { fetchAgents, fetchSkills, sendMessageStream, Agent, Skill, readFile, saveFile, openFileDialog, openFolderDialog, DirectoryItem } from './services/api';

const WORKFLOW_MODES = [
  { id: 'ask',    label: '[ ASK MAVERICK ]',   agent: 'mav-assistant', tab: null },
  { id: 'build',  label: '[ BUILD / FIX ]',     agent: 'mav-coder',     tab: 'editor' as const },
  { id: 'review', label: '[ REVIEW & REASON ]', agent: 'mav-research',  tab: null },
  { id: 'ops',    label: '[ OPS / DEBUG ]',     agent: 'mav-ops',       tab: null },
] as const;

type WorkflowModeId = typeof WORKFLOW_MODES[number]['id'];

interface Message {
  sender: 'USER' | 'PACC';
  content: string;
  model_used?: string;
  provider?: string;
  escalated?: boolean;
  error?: string;
}

export default function App() {
  const [input, setInput] = useState('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string>('');
  const [isEscalated, setIsEscalated] = useState(false);
  const [workflowMode, setWorkflowMode] = useState<WorkflowModeId>('ask');
  const [chatHistory, setChatHistory] = useState<Message[]>([
    {
      sender: 'PACC',
      content: 'System operational. All nodes reporting healthy. Maverick Core is online and awaiting instructions.',
    },
  ]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentTime, setCurrentTime] = useState('');
  const [tkns, setTkns] = useState('0.0');

  // Sidebar Workspace Tabs State
  const [activeTab, setActiveTab] = useState<'skills' | 'editor' | 'browser'>('skills');
  const [editorContent, setEditorContent] = useState('');
  const [editorFilePath, setEditorFilePath] = useState('C:\\Users\\carte\\pacc-gateway\\config.yaml');
  const [editorStatus, setEditorStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [editorStatusMsg, setEditorStatusMsg] = useState('');
  const [isDirMode, setIsDirMode] = useState(false);
  const [dirFiles, setDirFiles] = useState<DirectoryItem[]>([]);
  const [bootState, setBootState] = useState<'frame1' | 'frame2' | 'frame3' | 'frame4' | 'complete'>('frame1');
  
  // Preview states
  const [browserUrl, setBrowserUrl] = useState('http://localhost:3010');
  const [browserInputUrl, setBrowserInputUrl] = useState('http://localhost:3010');
  const [previewMode, setPreviewMode] = useState<'web' | 'monitor' | 'noc'>('web');
  const [screenshotRefreshKey, setScreenshotRefreshKey] = useState(Date.now());

  const chatEndRef = useRef<HTMLDivElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-focus prompt input box after generation finishes (with a small timeout to let the DOM re-enable it first)
  useEffect(() => {
    if (!isGenerating) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isGenerating]);

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsGenerating(false);
    }
  };

  const handleResetChat = () => {
    setChatHistory([
      {
        sender: 'PACC',
        content: 'System operational. All nodes reporting healthy. Maverick Core is online and awaiting instructions.',
      },
    ]);
  };

  const handleWorkflowSelect = (mode: typeof WORKFLOW_MODES[number]) => {
    setWorkflowMode(mode.id);
    setActiveAgentId(mode.agent);
    if (mode.tab) setActiveTab(mode.tab);
  };

  // Boot sequence transition effect
  useEffect(() => {
    const timer1 = setTimeout(() => setBootState('frame2'), 800);
    const timer2 = setTimeout(() => setBootState('frame3'), 2300);
    const timer3 = setTimeout(() => setBootState('frame4'), 3500);
    const timer4 = setTimeout(() => setBootState('complete'), 4500);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
    };
  }, []);

  // Time clock effect
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const timeStr = now.toISOString().replace('T', ' ').substring(11, 19) + ' UTC';
      setCurrentTime(timeStr);
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fluctuating TKN/S logic with slower 2.5-second update interval
  useEffect(() => {
    if (isGenerating) {
      setTkns((38.5 + Math.random() * 5.0).toFixed(1));
      const interval = setInterval(() => {
        const randomVal = (38.0 + Math.random() * 7.0).toFixed(1);
        setTkns(randomVal);
      }, 2500);
      return () => clearInterval(interval);
    } else {
      setTkns('0.0');
    }
  }, [isGenerating]);

  // Auto-refresh agent screenshots in monitor mode
  useEffect(() => {
    if (previewMode === 'monitor') {
      const interval = setInterval(() => {
        setScreenshotRefreshKey(Date.now());
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [previewMode]);

  // Fetch initial data & load default config file
  useEffect(() => {
    async function loadData() {
      try {
        const loadedAgents = await fetchAgents();
        setAgents(loadedAgents);
        if (loadedAgents.length > 0) {
          const defaultAgent = loadedAgents.find(a => a.agent_id === 'mav-assistant') || loadedAgents[0];
          setActiveAgentId(defaultAgent.agent_id);
        }
      } catch (e) {
        console.error('Failed to load agents', e);
      }

      try {
        const loadedSkills = await fetchSkills();
        setSkills(loadedSkills);
      } catch (e) {
        console.error('Failed to load skills', e);
      }
    }
    loadData();
    loadEditorFile(editorFilePath);
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const activeAgent = agents.find(a => a.agent_id === activeAgentId);

  // File loading helper
  const loadEditorFile = async (path: string) => {
    setEditorStatus('loading');
    setEditorStatusMsg('Reading path from host...');
    try {
      const res = await readFile(path);
      setEditorFilePath(res.path);
      if (res.is_directory) {
        setIsDirMode(true);
        setDirFiles(res.files || []);
        setEditorContent('');
        setEditorStatus('success');
        setEditorStatusMsg('Directory loaded successfully.');
      } else {
        setIsDirMode(false);
        setDirFiles([]);
        setEditorContent(res.content || '');
        setEditorStatus('success');
        setEditorStatusMsg('File loaded successfully.');
      }
    } catch (e: any) {
      setEditorStatus('error');
      setEditorStatusMsg(e.message || 'Failed to read path.');
    }
  };

  // File saving helper
  const handleSaveFile = async () => {
    if (isDirMode) return;
    setEditorStatus('loading');
    setEditorStatusMsg('Writing file to host...');
    try {
      await saveFile(editorFilePath, editorContent);
      setEditorStatus('success');
      setEditorStatusMsg('File saved successfully.');
    } catch (e: any) {
      setEditorStatus('error');
      setEditorStatusMsg(e.message || 'Failed to save file.');
    }
  };

  // Native explorer dialog picker helper
  const handleBrowseFile = async () => {
    try {
      setEditorStatus('loading');
      setEditorStatusMsg('Opening file explorer...');
      const res = await openFileDialog();
      if (res.status === 'success' && res.path) {
        setEditorFilePath(res.path);
        await loadEditorFile(res.path);
      } else {
        setEditorStatus('idle');
        setEditorStatusMsg('File selection cancelled.');
      }
    } catch (err: any) {
      setEditorStatus('error');
      setEditorStatusMsg(err.message || 'Failed to open file browser.');
    }
  };

  // Native explorer dialog folder picker helper
  const handleBrowseFolder = async () => {
    try {
      setEditorStatus('loading');
      setEditorStatusMsg('Opening folder explorer...');
      const res = await openFolderDialog();
      if (res.status === 'success' && res.path) {
        setEditorFilePath(res.path);
        await loadEditorFile(res.path);
      } else {
        setEditorStatus('idle');
        setEditorStatusMsg('Folder selection cancelled.');
      }
    } catch (err: any) {
      setEditorStatus('error');
      setEditorStatusMsg(err.message || 'Failed to open folder browser.');
    }
  };

  // Sync scroll between textarea and line gutter
  const handleScroll = () => {
    if (textareaRef.current && gutterRef.current) {
      gutterRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating || !activeAgentId) return;

    const userPrompt = input;
    setInput('');
    setIsGenerating(true);

    // Context-Aware Auto-Switching Triggers
    if (activeAgentId === 'mav-coder' || activeAgentId === 'goldenpathagent') {
      setActiveTab('editor');
      // Look for a Windows absolute path or simple filename in the query
      const winPathRegex = /[a-zA-Z]:\\[\\\w\.\-\_]+/g;
      const simpleFileRegex = /[\w\.\-\_]+\.(py|js|ts|tsx|json|yaml|yml|md|txt)/g;
      const matchWin = userPrompt.match(winPathRegex);
      if (matchWin && matchWin.length > 0) {
        loadEditorFile(matchWin[0]);
      } else {
        const matchSimple = userPrompt.match(simpleFileRegex);
        if (matchSimple && matchSimple.length > 0) {
          const pathName = matchSimple[0];
          const fullPath = `C:\\Users\\carte\\pacc-gateway\\${pathName}`;
          loadEditorFile(fullPath);
        }
      }
    } else if (activeAgentId === 'mav-research') {
      setActiveTab('browser');
      setPreviewMode('web'); // Switch to live web preview
      const urlRegex = /(https?:\/\/[^\s]+)/g;
      const match = userPrompt.match(urlRegex);
      if (match && match.length > 0) {
        setBrowserUrl(match[0]);
        setBrowserInputUrl(match[0]);
      }
    }

    // 1. Add user message
    setChatHistory(prev => [...prev, { sender: 'USER', content: userPrompt }]);

    // 2. Add placeholder PACC response that we will stream into
    setChatHistory(prev => [
      ...prev,
      {
        sender: 'PACC',
        content: '',
        model_used: 'connecting...',
        provider: 'none',
        escalated: isEscalated,
      },
    ]);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await sendMessageStream(
        userPrompt,
        activeAgentId,
        isEscalated,
        (chunk) => {
          setChatHistory(prev => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.sender === 'PACC') {
              const updatedMsg = {
                ...lastMsg,
                content: lastMsg.content + (chunk.content || ''),
                model_used: chunk.model_used || lastMsg.model_used,
                provider: chunk.provider || lastMsg.provider,
                escalated: chunk.escalated !== undefined ? chunk.escalated : lastMsg.escalated,
                error: chunk.error || lastMsg.error
              };
              return [...prev.slice(0, -1), updatedMsg];
            }
            return prev;
          });
        },
        editorFilePath,
        isDirMode ? "" : editorContent,
        controller.signal
      );
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Generation aborted by user');
      } else {
        console.error(err);
        setChatHistory(prev => {
          const next = [...prev];
          const lastMsg = next[next.length - 1];
          if (lastMsg && lastMsg.sender === 'PACC') {
            lastMsg.error = err.message || 'Unknown network error';
            if (!lastMsg.content) {
              lastMsg.content = 'Failed to execute query. Check backend logs.';
            }
          }
          return next;
        });
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="h-screen w-screen bg-mav-black text-mav-blue font-mono relative overflow-hidden p-2 flex flex-col gap-2">
      <div className="crt-overlay" />

      {/* --- MAVERICK CORE BOOT SEQUENCE OVERLAY --- */}
      {bootState !== 'complete' && (
        <div className={`fixed inset-0 bg-[#020205] z-50 flex flex-col items-center justify-center transition-opacity duration-1000 ${bootState === 'frame4' ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
          <div className={`w-[800px] h-[450px] relative flex items-center justify-center overflow-hidden transition-all duration-1000 transform ${bootState === 'frame4' ? '-translate-y-[120%]' : 'translate-y-0'}`}>
            {bootState !== 'frame1' && (
              <img
                src="/Maverick-Integrations-Logo-V2++16x9.png"
                alt="Maverick Core Logo"
                className={`w-full h-full object-contain ${
                  bootState === 'frame2' 
                    ? 'core-pulsing' 
                    : bootState === 'frame3' 
                      ? 'logo-glitch' 
                      : ''
                }`}
                style={
                  bootState === 'frame2'
                    ? { clipPath: 'inset(18% 30% 18% 30%)' }
                    : undefined
                }
              />
            )}
          </div>
        </div>
      )}

      {/* --- GHOST WATERMARK --- */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-5 z-0">
        <img src="/Maverick-Integrations-Logo-V2++16x9.png" alt="Maverick Core" className="w-5/6 object-contain" />
      </div>

      {/* --- GLOBAL HEADER --- */}
      <header className={`clipped-panel h-16 flex items-center justify-between px-4 shadow-glow-mav z-10 transition-transform duration-500 transform ${bootState === 'frame4' || bootState === 'complete' ? 'translate-y-0' : '-translate-y-[120%]'}`}>
        <div className="flex items-center gap-4">
          {/* BRAND LOGO */}
          <img src="/Maverick-Integrations-Logo-V2++.png" alt="Maverick Integrations" className="h-10 w-auto object-contain logo-breathing" />
          <div className="flex flex-col">
            <span className="font-black tracking-tighter text-white leading-none text-base">SYSTEM_OS</span>
            <span className="text-sm text-mav-chrome font-bold mt-0.5">LOCATION: DFW_TX</span>
          </div>
        </div>
        
        <div className="flex items-center gap-6 text-sm font-bold">
          <div className="flex items-center gap-2 text-white font-black">
            <span className="w-2.5 h-2.5 bg-mav-blue rounded-full animate-pulse" />
            <span>BRAIN: ONLINE (PROXMOX)</span>
          </div>
          <div className="flex items-center gap-2 text-white font-black">
            <span className="w-2.5 h-2.5 bg-mav-blue rounded-full animate-pulse" />
            <span>MAVERICK CORE STATUS: ONLINE</span>
          </div>
          <span className="text-white font-black text-base">{currentTime || '12:00:00 UTC'}</span>
          <button
            onClick={handleResetChat}
            className="px-2 py-1 bg-mav-dark border border-mav-blue/40 text-mav-chrome hover:text-white hover:border-mav-blue transition-all duration-150 text-[10px] font-black"
          >
            [ RESET_SESSION ]
          </button>
        </div>
      </header>

      {/* --- MAIN HUD AREA --- */}
      <main className="flex-1 flex gap-2 overflow-hidden z-10">
        
        {/* LEFT: Tabbed HUD Sidebar (Dynamic width: w-80 on skills, w-[38rem] on editor/browser) */}
        <aside className={`${activeTab === 'skills' ? 'w-80' : 'w-[38rem]'} flex flex-col gap-2 transition-all duration-300 transform ${bootState === 'frame4' || bootState === 'complete' ? 'translate-x-0' : '-translate-x-[120%]'}`}>
          <div className="clipped-panel flex-1 p-3 flex flex-col gap-3 overflow-hidden">
            
            {/* TACTICAL TABS */}
            <div className="flex gap-1 border-b border-mav-blue/30 pb-2">
              <button
                type="button"
                onClick={() => setActiveTab('skills')}
                className={`flex-1 py-1.5 text-center text-xs font-black tracking-tighter border transition-all duration-150 ${
                  activeTab === 'skills'
                    ? 'border-mav-blue bg-mav-blue/20 text-white shadow-glow-mav'
                    : 'border-transparent text-mav-blue/50 hover:text-white hover:bg-mav-blue/5'
                }`}
              >
                [ SKILLS ]
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('editor')}
                className={`flex-1 py-1.5 text-center text-xs font-black tracking-tighter border transition-all duration-150 ${
                  activeTab === 'editor'
                    ? 'border-mav-blue bg-mav-blue/20 text-white shadow-glow-mav'
                    : 'border-transparent text-mav-blue/50 hover:text-white hover:bg-mav-blue/5'
                }`}
              >
                [ EDITOR ]
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('browser')}
                className={`flex-1 py-1.5 text-center text-xs font-black tracking-tighter border transition-all duration-150 ${
                  activeTab === 'browser'
                    ? 'border-mav-blue bg-mav-blue/20 text-white shadow-glow-mav'
                    : 'border-transparent text-mav-blue/50 hover:text-white hover:bg-mav-blue/5'
                }`}
              >
                [ PREVIEW ]
              </button>
            </div>

            {/* TAB CONTENT: SKILLS */}
            {activeTab === 'skills' && (
              <div className="flex-1 flex flex-col gap-1.5 overflow-y-auto pr-1">
                <h3 className="text-sm font-black text-white border-b border-mav-blue/30 pb-1">AUTHORIZED_SKILLS</h3>
                {skills
                  .filter(skill => activeAgent?.authorized_skills?.includes(skill.skill_id))
                  .map(skill => {
                    const status = isGenerating ? 'executing' : 'ready';
                    return (
                      <div key={skill.skill_id} className="flex flex-col gap-0.5 text-xs p-1.5 bg-mav-dark border border-mav-blue/50">
                        <div className="flex items-center justify-between">
                          <span className="font-black text-white">{skill.skill_id.toUpperCase()}</span>
                          <span className={`uppercase font-black text-[10px] ${status === 'ready' ? 'text-mav-blue' : 'text-neon-green animate-pulse'}`}>
                            [{status}]
                          </span>
                        </div>
                        <span className="text-mav-chrome font-medium text-[11px] leading-normal mt-0.5">{skill.description}</span>
                      </div>
                    );
                  })}
                {skills.filter(skill => activeAgent?.authorized_skills?.includes(skill.skill_id)).length === 0 && (
                  <div className="text-xs opacity-50 italic text-white">No authorized skills for this agent.</div>
                )}
              </div>
            )}

            {/* TAB CONTENT: EDITOR */}
            {activeTab === 'editor' && (
              <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                {/* File path selector */}
                <div className="flex items-center gap-1 text-xs">
                  <span className="text-mav-blue font-bold tracking-tight">PATH:</span>
                  <input
                    type="text"
                    className="flex-1 bg-mav-black border border-mav-blue/40 px-2 py-1 text-mav-chrome font-mono focus:border-mav-blue outline-none"
                    value={editorFilePath}
                    onChange={(e) => setEditorFilePath(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        loadEditorFile(editorFilePath);
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleBrowseFile}
                    className="px-2 py-1 bg-mav-blue/20 border border-mav-blue hover:bg-mav-blue/45 text-white font-bold"
                    title="Select a file"
                  >
                    [ FILE ]
                  </button>
                  <button
                    type="button"
                    onClick={handleBrowseFolder}
                    className="px-2 py-1 bg-mav-blue/20 border border-mav-blue hover:bg-mav-blue/45 text-white font-bold"
                    title="Select a folder"
                  >
                    [ FOLDER ]
                  </button>
                  <button
                    type="button"
                    onClick={() => loadEditorFile(editorFilePath)}
                    className="px-2 py-1 bg-mav-blue/20 border border-mav-blue hover:bg-mav-blue/40 text-white font-bold"
                  >
                    LOAD
                  </button>
                </div>

                {/* Synced Code Area or Workspace Directory Explorer */}
                <div className="flex-1 border border-mav-blue/40 bg-mav-black flex overflow-hidden relative font-mono text-sm leading-relaxed mt-1">
                  {isDirMode ? (
                    <div className="flex-1 flex flex-col overflow-y-auto p-3 gap-1.5 select-none text-xs">
                      {/* Parent Directory Navigation */}
                      <div 
                        onClick={() => {
                          let cleanPath = editorFilePath.replace(/[\\/]+$/, '');
                          const lastIdx = Math.max(cleanPath.lastIndexOf('\\'), cleanPath.lastIndexOf('/'));
                          if (lastIdx > 0) {
                            const parentPath = cleanPath.substring(0, lastIdx);
                            loadEditorFile(parentPath.endsWith(':') ? parentPath + '\\' : parentPath);
                          } else if (cleanPath.includes(':')) {
                            loadEditorFile(cleanPath + '\\');
                          }
                        }}
                        className="cursor-pointer hover:bg-mav-blue/10 p-1.5 border border-transparent hover:border-mav-blue/20 text-mav-blue font-bold flex items-center gap-2"
                      >
                        <span>📁</span>
                        <span>[..] Parent Directory</span>
                      </div>
                      
                      {dirFiles.map((file, idx) => (
                        <div 
                          key={idx}
                          onClick={() => loadEditorFile(file.path)}
                          className={`cursor-pointer p-2 border border-transparent hover:border-mav-blue/35 hover:bg-mav-blue/10 flex items-center justify-between transition-all duration-100 ${file.is_dir ? 'text-white font-bold' : 'text-mav-chrome'}`}
                        >
                          <div className="flex items-center gap-2">
                            <span>{file.is_dir ? '📁' : '📄'}</span>
                            <span>{file.name}</span>
                          </div>
                          <span className="text-[10px] opacity-40 uppercase">
                            {file.is_dir ? '[DIR]' : '[FILE]'}
                          </span>
                        </div>
                      ))}
                      
                      {dirFiles.length === 0 && (
                        <div className="p-4 text-center opacity-50 italic text-white">Empty Directory</div>
                      )}
                    </div>
                  ) : (
                    <>
                      {/* Gutter */}
                      <div
                        ref={gutterRef}
                        className="w-12 bg-mav-dark/80 text-mav-blue/40 text-right pr-2 select-none py-2 border-r border-mav-blue/20 overflow-hidden"
                        style={{ minHeight: '100%' }}
                      >
                        {editorContent.split('\n').map((_, idx) => (
                          <div key={idx} className="h-[22px] text-xs font-bold leading-[22px]">
                            {idx + 1}
                          </div>
                        ))}
                      </div>
                      
                      {/* Textarea */}
                      <textarea
                        ref={textareaRef}
                        className="flex-1 bg-transparent border-none outline-none resize-none p-2 text-mav-chrome font-mono text-xs leading-[22px] overflow-auto h-full"
                        value={editorContent}
                        onChange={(e) => setEditorContent(e.target.value)}
                        onScroll={handleScroll}
                        spellCheck={false}
                      />
                    </>
                  )}
                </div>

                {/* Status message */}
                {editorStatusMsg && (
                  <div className={`text-[11px] font-bold ${editorStatus === 'success' ? 'text-neon-green' : editorStatus === 'error' ? 'text-mav-alert' : 'text-mav-blue animate-pulse'}`}>
                    &gt; {editorStatusMsg.toUpperCase()}
                  </div>
                )}

                {/* Editor Controls */}
                <div className="flex gap-2 mt-1">
                  <button
                    type="button"
                    onClick={handleSaveFile}
                    disabled={editorStatus === 'loading'}
                    className="flex-1 py-1.5 bg-mav-blue/20 border border-mav-blue text-white font-bold text-xs hover:bg-mav-blue/45 disabled:opacity-50"
                  >
                    [ SAVE CHANGES ]
                  </button>
                  <button
                    type="button"
                    onClick={() => loadEditorFile(editorFilePath)}
                    disabled={editorStatus === 'loading'}
                    className="px-3 py-1.5 bg-mav-dark border border-mav-blue/40 text-mav-chrome font-bold text-xs hover:border-mav-blue disabled:opacity-50"
                  >
                    REVERT
                  </button>
                </div>
              </div>
            )}

            {/* TAB CONTENT: PREVIEW */}
            {activeTab === 'browser' && (
              <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                {/* Preview Mode Selector */}
                <div className="flex gap-1 border-b border-mav-blue/20 pb-1.5 mb-1">
                  <button
                    type="button"
                    onClick={() => setPreviewMode('web')}
                    className={`flex-1 py-1 text-center text-[10px] font-black border transition-all duration-150 ${
                      previewMode === 'web'
                        ? 'border-mav-blue bg-mav-blue/15 text-white'
                        : 'border-transparent text-mav-blue/40 hover:text-white hover:bg-mav-blue/5'
                    }`}
                  >
                    [ LIVE WEB PREVIEW ]
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewMode('monitor')}
                    className={`flex-1 py-1 text-center text-[10px] font-black border transition-all duration-150 ${
                      previewMode === 'monitor'
                        ? 'border-mav-blue bg-mav-blue/15 text-white'
                        : 'border-transparent text-mav-blue/40 hover:text-white hover:bg-mav-blue/5'
                    }`}
                  >
                    [ AGENT SCREEN MONITOR ]
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewMode('noc')}
                    className={`flex-1 py-1 text-center text-[10px] font-black border transition-all duration-150 ${
                      previewMode === 'noc'
                        ? 'border-mav-blue bg-mav-blue/15 text-white'
                        : 'border-transparent text-mav-blue/40 hover:text-white hover:bg-mav-blue/5'
                    }`}
                  >
                    [ NOC DASHBOARD ]
                  </button>
                </div>

                {previewMode === 'web' ? (
                  <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                    {/* Address input */}
                    <div className="flex items-center gap-1.5 text-xs">
                      <span className="text-mav-blue font-bold tracking-tight">URL/PATH:</span>
                      <input
                        type="text"
                        className="flex-1 bg-mav-black border border-mav-blue/40 px-2 py-1 text-mav-chrome font-mono focus:border-mav-blue outline-none"
                        value={browserInputUrl}
                        onChange={(e) => setBrowserInputUrl(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            setBrowserUrl(browserInputUrl);
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setBrowserInputUrl(editorFilePath);
                          setBrowserUrl(editorFilePath);
                        }}
                        className="px-2 py-1 bg-mav-blue/20 border border-mav-blue hover:bg-mav-blue/45 text-white font-bold animate-pulse"
                        title="Preview the active file from the editor"
                      >
                        [ ACTIVE FILE ]
                      </button>
                      <button
                        type="button"
                        onClick={() => setBrowserUrl(browserInputUrl)}
                        className="px-2 py-1 bg-mav-blue/20 border border-mav-blue hover:bg-mav-blue/40 text-white font-bold"
                      >
                        GO
                      </button>
                    </div>

                    {/* IFrame viewport */}
                    <div className="flex-1 border border-mav-blue/40 bg-white relative mt-1 overflow-hidden">
                      <iframe
                        src={
                          browserUrl.startsWith('http://') || browserUrl.startsWith('https://')
                            ? browserUrl
                            : `http://localhost:8000/preview?path=${encodeURIComponent(browserUrl)}`
                        }
                        className="w-full h-full border-none"
                        title="Tactical HUD Web Preview"
                      />
                    </div>

                    <div className="text-[10px] text-mav-chrome/60 italic leading-snug">
                      * Note: Local HTML paths (e.g. C:\path\to\landing.html) are rendered automatically via Gateway preview.
                    </div>
                  </div>
                ) : previewMode === 'monitor' ? (
                  <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                    <div className="text-[11px] text-white font-bold border-b border-mav-blue/30 pb-1 mb-1">
                      &gt; BROWSER AGENT ACTIVITY MONITOR...
                    </div>
                    {/* Live image viewport */}
                    <div className="flex-1 border border-mav-blue/40 bg-mav-black relative mt-1 overflow-hidden flex items-center justify-center">
                      <img
                        src={`http://localhost:8000/browser-screenshot?t=${screenshotRefreshKey}`}
                        className="w-full h-full object-contain"
                        alt="Agent Screen Monitor (No active screen)"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = '/logo-landscape.png';
                        }}
                      />
                    </div>
                    <div className="text-[10px] text-neon-green/80 italic leading-snug">
                      * Displaying live-updating viewport screenshot of the running browser subagent (refreshes every 2s).
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                    <div className="text-[11px] text-white font-bold border-b border-mav-blue/30 pb-1 mb-1 flex items-center gap-2">
                      <span className="w-2 h-2 bg-neon-green rounded-full animate-pulse" />
                      &gt; HOMELAB NOC DASHBOARD LINKED...
                    </div>
                    {/* NOC iframe viewport */}
                    <div className="flex-1 border border-mav-blue/40 bg-mav-black relative mt-1 overflow-hidden">
                      <iframe
                        src="http://localhost:3010"
                        className="w-full h-full border-none"
                        title="Homelab NOC Dashboard"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* CENTER: The Console Log (Flexible remaining space) */}
        <section className={`flex-1 flex flex-col gap-2 overflow-hidden transition-all duration-300 transform ${bootState === 'frame4' || bootState === 'complete' ? 'translate-y-0' : 'translate-y-[120%]'}`}>
          <div className="clipped-panel flex-1 p-4 overflow-y-auto flex flex-col gap-2 shadow-inner bg-mav-dark/50 backdrop-blur-sm">
            <div className="text-mav-chrome opacity-50 text-[10px] mb-4 italic">
              &gt; INITIALIZING MAVERICK CORE... <br />
              &gt; HANDSHAKE VERIFIED. <br />
              &gt; READY FOR INPUT.
            </div>
            
            <div className="flex flex-col gap-4">
              {chatHistory.map((msg, i) => (
                <div key={i} className="flex flex-col gap-1">
                  <div className="flex gap-2">
                    <span className={`${msg.sender === 'USER' ? 'text-white' : 'text-mav-blue'} font-bold`}>
                      {msg.sender} &gt;
                    </span>
                    <span className="text-mav-chrome whitespace-pre-wrap">{msg.content}</span>
                  </div>
                  {msg.sender === 'PACC' && (msg.model_used || msg.provider) && (
                    <div className="text-[9px] opacity-50 pl-14 flex items-center gap-3">
                      <span>MODEL: {msg.model_used}</span>
                      <span>PROVIDER: {msg.provider}</span>
                      {msg.escalated && <span className="text-mav-alert font-bold">☁️ ESCALATED</span>}
                    </div>
                  )}
                  {msg.error && (
                    <div className="text-[9px] text-mav-alert pl-14 font-semibold">
                      ⚠️ ERROR: {msg.error}
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Workflow Mode Selector */}
          <div className="clipped-panel flex gap-1 p-1.5 shadow-glow-mav">
            {WORKFLOW_MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                disabled={isGenerating}
                onClick={() => handleWorkflowSelect(mode)}
                className={`flex-1 py-1.5 text-center text-[11px] font-black border transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${
                  workflowMode === mode.id
                    ? mode.id === 'build'
                      ? 'border-mav-amber-glow/80 bg-mav-amber/10 text-mav-amber-glow shadow-glow-amber'
                      : 'border-mav-blue/80 bg-mav-blue/20 text-white shadow-glow-mav'
                    : 'border-mav-blue/25 text-mav-blue/50 hover:text-white hover:border-mav-blue/60 hover:bg-mav-blue/5'
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          {/* Command Palette */}
          <form onSubmit={handleSubmit} className="clipped-panel h-16 p-2 flex items-center gap-3 shadow-glow-mav">
            <span className="text-mav-blue font-bold pl-2">CMD &gt;</span>
            <input
              ref={inputRef}
              type="text"
              className="bg-transparent border-none outline-none flex-1 text-mav-chrome placeholder-mav-blue/30"
              placeholder={isGenerating ? 'Awaiting response stream...' : 'Enter command or ask active agent...'}
              value={input}
              disabled={isGenerating}
              onChange={(e) => setInput(e.target.value)}
            />
            {isGenerating && (
              <button
                type="button"
                onClick={handleStopGeneration}
                className="px-3 py-1 bg-mav-alert/20 border border-mav-alert text-mav-alert font-black text-xs hover:bg-mav-alert hover:text-white transition-all duration-150"
              >
                [ STOP_GEN ]
              </button>
            )}
          </form>
        </section>

        {/* RIGHT: Agent Roster (Narrower: w-48 / 192px) */}
        <aside className={`w-48 flex flex-col gap-2 transition-all duration-300 transform ${bootState === 'frame4' || bootState === 'complete' ? 'translate-x-0' : 'translate-x-[120%]'}`}>
          <div className="clipped-panel flex-1 p-3 flex flex-col gap-3 overflow-y-auto">
            <h3 className="text-sm font-black mb-2 text-white border-b border-mav-blue pb-1.5">AGENT_ROSTER</h3>
            {agents.map(agent => {
              const isActive = activeAgentId === agent.agent_id;
              const isAgentThinking = isActive && isGenerating;
              return (
                <div 
                  key={agent.agent_id} 
                  onClick={() => !isGenerating && setActiveAgentId(agent.agent_id)}
                  className={`cursor-pointer p-2.5 border transition-all duration-200 ${
                    isActive 
                      ? 'border-mav-blue/80 bg-mav-blue/20 shadow-glow-mav' 
                      : 'border-mav-blue/40 bg-mav-dark hover:border-mav-blue/70'
                  }`}
                >
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className={isActive ? 'text-white font-black shadow-glow-mav' : 'text-white font-bold'}>
                        {agent.name}
                      </span>
                      <span className={`w-2 h-2 rounded-full ${isAgentThinking ? 'bg-neon-green animate-ping' : 'bg-mav-blue'}`} />
                    </div>
                    <span className="text-xs text-mav-chrome font-bold mt-1">
                      {agent.primary_model}
                    </span>
                  </div>
                </div>
              );
            })}
            {agents.length === 0 && (
              <div className="text-sm opacity-50 italic text-white">Loading agent registry...</div>
            )}
          </div>
        </aside>
      </main>

      {/* --- TELEMETRY STRIP --- */}
      <footer className={`clipped-panel h-12 flex items-center justify-between px-4 text-sm shadow-glow-mav z-10 font-bold text-white transition-transform duration-500 transform ${bootState === 'frame4' || bootState === 'complete' ? 'translate-y-0' : 'translate-y-[120%]'}`}>
        <div className="flex items-center gap-6">
          {/* Concentric Energy Ring Gauge */}
          <div className="flex items-center gap-3">
            <span className="text-mav-chrome font-bold text-xs uppercase tracking-wider">MAVERICK CORE STATUS:</span>
            <div className="relative w-10 h-10 flex items-center justify-center">
              {/* Background ring */}
              <svg className="absolute w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <circle
                  cx="18"
                  cy="18"
                  r="16"
                  fill="none"
                  stroke="#020205"
                  strokeWidth="3.5"
                />
                {/* Outer dashed ring (static/background) */}
                <circle
                  cx="18"
                  cy="18"
                  r="16"
                  fill="none"
                  stroke="#00A3FF"
                  strokeWidth="1.5"
                  strokeDasharray="4, 2"
                  className="opacity-25"
                />
                {/* Active segment ring (shows VRAM / Core status) */}
                <circle
                  cx="18"
                  cy="18"
                  r="16"
                  fill="none"
                  stroke="#00A3FF"
                  strokeWidth="2.5"
                  strokeDasharray="100"
                  strokeDashoffset={100 - 65}
                  className="shadow-glow-mav transition-all duration-500"
                  strokeLinecap="round"
                />
              </svg>
              {/* Inner spinning energy ring */}
              <svg className="absolute w-7 h-7 animate-spin-slow" viewBox="0 0 36 36">
                <circle
                  cx="18"
                  cy="18"
                  r="13"
                  fill="none"
                  stroke="#00A3FF"
                  strokeWidth="1.5"
                  strokeDasharray="6, 8"
                  className="opacity-75"
                />
              </svg>
              <span className="text-[9px] text-white font-black">65%</span>
            </div>
          </div>
          <div className="flex items-center gap-2 text-white">
            <span className="text-mav-chrome font-bold">TKN/S:</span>
            <span className="text-white font-bold text-sm">{tkns}</span>
          </div>
        </div>

        <button 
          onClick={() => setIsEscalated(prev => !prev)}
          className={`px-4 py-1.5 font-black text-sm transition-all duration-200 uppercase flex items-center gap-2 ${
            isEscalated 
              ? 'bg-mav-alert text-white shadow-glow-alert animate-pulse border border-red-600' 
              : 'bg-mav-dark text-white border border-mav-blue/40 hover:border-mav-alert hover:text-mav-alert'
          }`}
        >
          ⚠️ {isEscalated ? 'Forcing Cloud Escalation' : 'Escalate to Cloud'}
        </button>
      </footer>
    </div>
  );
}
