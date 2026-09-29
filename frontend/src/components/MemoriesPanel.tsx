import type { MemoryUsed } from '../types/review';

interface MemoriesPanelProps {
  memories: MemoryUsed[];
}

export function MemoriesPanel({ memories }: MemoriesPanelProps) {
  if (memories.length === 0) {
    return (
      <div className="memories-panel empty">
        <div className="empty-state">
          <svg className="brain-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M12 2a8 8 0 0 0-8 8c0 4.4 4 8 8 8s8-3.6 8-8a8 8 0 0 0-8-8z" />
            <path d="M12 6v4" />
            <path d="M12 14v4" />
            <path d="M8 10h8" />
            <path d="M8 14h8" />
          </svg>
          <p>No team memories were recalled for this review</p>
        </div>
      </div>
    );
  }

  return (
    <div className="memories-panel">
      <div className="memories-header">
        <h3>
          <svg className="brain-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a8 8 0 0 0-8 8c0 4.4 4 8 8 8s8-3.6 8-8a8 8 0 0 0-8-8z" />
            <path d="M12 6v4" />
            <path d="M12 14v4" />
            <path d="M8 10h8" />
            <path d="M8 14h8" />
          </svg>
          🧠 Memories Used ({memories.length})
        </h3>
        <p className="memories-subtitle">
          These team memories from Hindsight informed the review recommendations above
        </p>
      </div>

      <div className="memories-list">
        {memories.map((memory, index) => (
          <MemoryCard key={memory.id} memory={memory} index={index + 1} />
        ))}
      </div>
    </div>
  );
}

interface MemoryCardProps {
  memory: MemoryUsed;
  index: number;
}

function MemoryCard({ memory, index }: MemoryCardProps) {
  return (
    <div className="memory-card">
      <div className="memory-header">
        <span className="memory-index">#{index}</span>
        <span className="memory-type">{memory.type || 'observation'}</span>
      </div>
      <p className="memory-text">{memory.text}</p>
      {memory.context && (
        <p className="memory-context"><strong>Context:</strong> {memory.context}</p>
      )}
      {memory.metadata && Object.keys(memory.metadata).length > 0 && (
        <details className="memory-metadata">
          <summary>Metadata</summary>
          <pre>{JSON.stringify(memory.metadata, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}