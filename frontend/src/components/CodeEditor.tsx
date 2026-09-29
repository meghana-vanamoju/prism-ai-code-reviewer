import { useState } from 'react';
import type { ChangeEvent } from 'react';
import type { ReviewRequest } from '../types/review';

interface CodeEditorProps {
  onSubmit: (request: ReviewRequest) => void;
  isLoading: boolean;
  defaultCode?: string;
}

export function CodeEditor({ onSubmit, isLoading, defaultCode }: CodeEditorProps) {
  const [code, setCode] = useState(defaultCode || '');
  const [language, setLanguage] = useState('javascript');
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    onSubmit({ code, language, query: query || undefined });
  };

  const handleCodeChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setCode(e.target.value);
  };

  return (
    <form onSubmit={handleSubmit} className="code-editor-section">
      <div className="editor-header">
        <h2>Code to Review</h2>
        <div className="editor-controls">
          <select value={language} onChange={(e) => setLanguage(e.target.value)} className="language-select">
            <option value="javascript">JavaScript</option>
            <option value="typescript">TypeScript</option>
            <option value="python">Python</option>
            <option value="go">Go</option>
            <option value="rust">Rust</option>
            <option value="java">Java</option>
            <option value="cpp">C++</option>
            <option value="other">Other</option>
          </select>
        </div>
      </div>

      <textarea
        value={code}
        onChange={handleCodeChange}
        placeholder="Paste your code here for review..."
        className="code-textarea"
        rows={20}
        spellCheck={false}
      />

      <div className="review-options">
        <div className="query-input">
          <label htmlFor="query">Specific review focus (optional)</label>
          <input
            id="query"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., financial calculation issues, security concerns, performance"
          />
        </div>
        <button type="submit" className="review-button" disabled={isLoading || !code.trim()}>
          {isLoading ? 'Reviewing...' : 'Review Code'}
        </button>
      </div>
    </form>
  );
}