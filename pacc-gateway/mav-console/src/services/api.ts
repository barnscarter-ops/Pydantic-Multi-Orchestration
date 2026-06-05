export interface Agent {
  agent_id: string;
  name: string;
  system_prompt: string;
  primary_model: string;
  fallback_model: string;
  authorized_skills: string[];
  params: {
    temperature: number;
    max_tokens: number;
    context_window: number;
    top_p: number;
  };
}

export interface Skill {
  skill_id: string;
  description: string;
  exec_command: string;
  args_schema: Record<string, any>;
}

export interface StreamChunk {
  content: string;
  model_used: string;
  provider: string;
  escalated: boolean;
  error?: string;
}

const REGISTRY_URL = 'http://192.168.1.12:8001';
const GATEWAY_URL = 'http://localhost:8000';

export async function fetchAgents(): Promise<Agent[]> {
  const response = await fetch(`${REGISTRY_URL}/agents`);
  if (!response.ok) {
    throw new Error(`Failed to fetch agents: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchSkills(): Promise<Skill[]> {
  const response = await fetch(`${REGISTRY_URL}/skills`);
  if (!response.ok) {
    throw new Error(`Failed to fetch skills: ${response.statusText}`);
  }
  return response.json();
}

export async function sendMessageStream(
  prompt: string,
  agentId: string,
  forceEscalate: boolean,
  onChunk: (chunk: StreamChunk) => void
): Promise<void> {
  const response = await fetch(`${GATEWAY_URL}/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt,
      agent_id: agentId,
      stream: true,
      force_escalate: forceEscalate,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body stream reader available');
  }

  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim()) {
          try {
            const chunk: StreamChunk = JSON.parse(line);
            onChunk(chunk);
          } catch (e) {
            console.error('Failed to parse JSON stream line:', line, e);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
