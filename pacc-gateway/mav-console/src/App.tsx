import React, { useState, useEffect, useRef } from 'react';
import { fetchAgents, fetchSkills, sendMessageStream, Agent, Skill } from './services/api';

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
  const [chatHistory, setChatHistory] = useState<Message[]>([
    {
      sender: 'PACC',
      content: 'System operational. All nodes reporting healthy. Maverick Core is online and awaiting instructions.',
    },
  ]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentTime, setCurrentTime] = useState('');

  const chatEndRef = useRef<HTMLDivElement>(null);

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

  // Fetch initial data
  useEffect(() => {
    async function loadData() {
      try {
        const loadedAgents = await fetchAgents();
        setAgents(loadedAgents);
        if (loadedAgents.length > 0) {
          // Find coder as default or use the first agent
          const defaultAgent = loadedAgents.find(a => a.agent_id === 'mav-coder') || loadedAgents[0];
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
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const activeAgent = agents.find(a => a.agent_id === activeAgentId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating || !activeAgentId) return;

    const userPrompt = input;
    setInput('');
    setIsGenerating(true);

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
        }
      );
    } catch (err: any) {
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
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="h-screen w-screen bg-mav-black text-mav-blue font-mono relative overflow-hidden p-2 flex flex-col gap-2">
      <div className="crt-overlay" />

      {/* --- GHOST WATERMARK --- */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-5 z-0">
        <img src="/logo-full.png" alt="Maverick Core" className="w-2/3 object-contain" />
      </div>

      {/* --- GLOBAL HEADER --- */}
      <header className="clipped-panel h-16 flex items-center justify-between px-4 shadow-glow-mav z-10">
        <div className="flex items-center gap-4">
          {/* BRAND LOGO */}
          <img src="/logo-landscape.png" alt="Maverick Integrations" className="h-10 w-auto object-contain" />
          <div className="flex flex-col">
            <span className="font-bold tracking-tighter text-mav-chrome leading-none">SYSTEM_OS</span>
            <span className="text-[10px] opacity-50">LOCATION: DFW_TX</span>
          </div>
        </div>
        
        <div className="flex items-center gap-6 text-xs">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-mav-blue rounded-full animate-pulse" />
            <span>BRAIN: ONLINE (PROXMOX)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-mav-blue rounded-full animate-pulse" />
            <span>MUSCLE: ACTIVE (PC)</span>
          </div>
          <span className="text-mav-chrome font-bold">{currentTime || '12:00:00 UTC'}</span>
        </div>
      </header>

      {/* --- MAIN HUD AREA --- */}
      <main className="flex-1 flex gap-2 overflow-hidden z-10">
        
        {/* LEFT: Skill Manifest */}
        <aside className="w-64 flex flex-col gap-2">
          <div className="clipped-panel flex-1 p-3 flex flex-col gap-3 overflow-y-auto">
            <h3 className="text-xs font-bold mb-2 opacity-70 border-b border-mav-blue/30 pb-1">AUTHORIZED_SKILLS</h3>
            {skills.map(skill => {
              const isAuthorized = activeAgent?.authorized_skills?.includes(skill.skill_id);
              const status = isAuthorized ? (isGenerating ? 'executing' : 'ready') : 'locked';
              return (
                <div key={skill.skill_id} className="flex flex-col gap-1 text-[10px] p-2 bg-mav-dark border border-mav-blue/20">
                  <div className="flex items-center justify-between">
                    <span className="font-bold">{skill.skill_id.toUpperCase()}</span>
                    <span className={`uppercase ${status === 'ready' ? 'text-mav-blue' : status === 'executing' ? 'text-neon-green animate-pulse' : 'text-mav-alert'}`}>
                      [{status}]
                    </span>
                  </div>
                  <span className="opacity-50 text-[9px] leading-tight">{skill.description}</span>
                </div>
              );
            })}
            {skills.length === 0 && (
              <div className="text-[10px] opacity-50 italic">No skills registered.</div>
            )}
          </div>
        </aside>

        {/* CENTER: The Console Log */}
        <section className="flex-1 flex flex-col gap-2 overflow-hidden">
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

          {/* Command Palette */}
          <form onSubmit={handleSubmit} className="clipped-panel h-16 p-2 flex items-center gap-3 shadow-glow-mav">
            <span className="text-mav-blue font-bold pl-2">CMD &gt;</span>
            <input 
              type="text" 
              className="bg-transparent border-none outline-none flex-1 text-mav-chrome placeholder-mav-blue/30"
              placeholder={isGenerating ? 'Awaiting response stream...' : 'Enter command or ask active agent...'}
              value={input}
              disabled={isGenerating}
              onChange={(e) => setInput(e.target.value)}
            />
          </form>
        </section>

        {/* RIGHT: Agent Roster */}
        <aside className="w-64 flex flex-col gap-2">
          <div className="clipped-panel flex-1 p-3 flex flex-col gap-3 overflow-y-auto">
            <h3 className="text-xs font-bold mb-2 opacity-70 border-b border-mav-blue/30 pb-1">AGENT_ROSTER</h3>
            {agents.map(agent => {
              const isActive = activeAgentId === agent.agent_id;
              const isAgentThinking = isActive && isGenerating;
              return (
                <div 
                  key={agent.agent_id} 
                  onClick={() => !isGenerating && setActiveAgentId(agent.agent_id)}
                  className={`cursor-pointer p-2 border transition-all duration-200 ${
                    isActive 
                      ? 'border-mav-blue bg-mav-blue/10 shadow-glow-mav' 
                      : 'border-mav-blue/20 bg-mav-dark hover:border-mav-blue/50'
                  }`}
                >
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className={isActive ? 'text-mav-blue font-bold' : 'text-mav-chrome'}>
                        {agent.name}
                      </span>
                      <span className={`w-2 h-2 rounded-full ${isAgentThinking ? 'bg-neon-green animate-ping' : 'bg-mav-blue'}`} />
                    </div>
                    <span className="text-[9px] opacity-50 leading-tight">
                      {agent.primary_model}
                    </span>
                  </div>
                </div>
              );
            })}
            {agents.length === 0 && (
              <div className="text-xs opacity-50 italic">Loading agent registry...</div>
            )}
          </div>
        </aside>
      </main>

      {/* --- TELEMETRY STRIP --- */}
      <footer className="clipped-panel h-10 flex items-center justify-between px-4 text-[10px] shadow-glow-mav z-10">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span>VRAM:</span>
            <div className="w-24 h-2 bg-mav-black border border-mav-blue/30 relative">
              <div className="absolute top-0 left-0 h-full bg-mav-blue shadow-glow-mav" style={{width: '65%'}} />
            </div>
            <span className="text-mav-chrome">65%</span>
          </div>
          <div className="flex items-center gap-2">
            <span>TKN/S:</span>
            <span className="text-mav-chrome font-bold">{isGenerating ? '48.2' : '0.0'}</span>
          </div>
        </div>

        <button 
          onClick={() => setIsEscalated(prev => !prev)}
          className={`px-3 py-1 font-bold transition-all duration-200 uppercase flex items-center gap-2 ${
            isEscalated 
              ? 'bg-mav-alert text-white shadow-glow-alert animate-pulse border border-red-600' 
              : 'bg-mav-dark text-mav-chrome border border-mav-blue/30 hover:border-mav-alert hover:text-mav-alert'
          }`}
        >
          ⚠️ {isEscalated ? 'Forcing Cloud Escalation' : 'Escalate to Cloud'}
        </button>
      </footer>
    </div>
  );
}