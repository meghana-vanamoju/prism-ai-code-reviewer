import { useEffect, useMemo, useRef, useState } from 'react';
import type { DiffLine, FileDiff, FileSummary, ReviewResult } from '../types/job';
import type { Issue } from '../types/review';

interface CodeViewerProps {
  result: ReviewResult;
  selectedFile: string;
  onSelectFile: (path: string) => void;
  focusLine: number | null;
  onIssueFocusHandled: () => void;
}

type ViewMode = 'diff' | 'code';

/** Renders the review workspace: file list on the left, code/diff on the right. */
export function CodeViewer({
  result,
  selectedFile,
  onSelectFile,
  focusLine,
  onIssueFocusHandled,
}: CodeViewerProps) {
  const files = result.files;
  const activeFile = files.find((f) => f.path === selectedFile) ?? files[0];
  const diff = result.diffs.find((d) => d.path === activeFile?.path);
  const [view, setView] = useState<ViewMode>('diff');

  const statByPath = useMemo(() => {
    const map = new Map<string, { add: number; del: number }>();
    for (const entry of result.diffs) {
      let add = 0;
      let del = 0;
      for (const hunk of entry.hunks) {
        for (const line of hunk.lines) {
          if (line.type === 'add') add += 1;
          else if (line.type === 'del') del += 1;
        }
      }
      map.set(entry.path, { add, del });
    }
    return map;
  }, [result.diffs]);

  const activeStat = activeFile ? statByPath.get(activeFile.path) : undefined;

  const hasContent = Boolean(activeFile?.content);
  const available: ViewMode[] = diff ? (hasContent ? ['diff', 'code'] : ['diff']) : ['code'];
  const effectiveView: ViewMode = available.includes(view) ? view : available[0];

  return (
    <div className="viewer-panel">
      <div className="file-panel">
        <div className="file-panel-header">
          <span>Files</span>
          <span>{files.length}</span>
        </div>
        <div className="file-list">
          {files.map((file) => {
            const stat = statByPath.get(file.path);
            return (
              <button
                key={file.path}
                type="button"
                className={`file-item ${file.path === activeFile?.path ? 'selected' : ''}`.trim()}
                onClick={() => onSelectFile(file.path)}
                title={file.skip_reason ?? file.path}
              >
                <span className={`file-dot lang-${file.language}`} aria-hidden="true" />
                <span className="file-name">{file.path}</span>
                {stat && (
                  <span className="diff-stat">
                    <span className="diff-add">+{stat.add}</span>
                    <span className="diff-del">−{stat.del}</span>
                  </span>
                )}
                {file.skipped ? (
                  <span className="skipped-mark">skipped</span>
                ) : (
                  <span className={`issue-count ${file.issue_count === 0 ? 'zero' : ''}`.trim()}>
                    {file.issue_count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="code-view">
        <div className="code-view-header">
          <span className="code-view-path">
            <span className={`file-dot lang-${activeFile?.language ?? 'other'}`} aria-hidden="true" />
            {activeFile?.path ?? '—'}
          </span>
          <span className="code-view-tools">
            {activeStat && (
              <span className="diff-stat">
                <span className="diff-add">+{activeStat.add}</span>
                <span className="diff-del">−{activeStat.del}</span>
              </span>
            )}
            {available.length > 1 && (
              <div className="view-toggle">
                {available.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={effectiveView === mode ? 'active' : ''}
                    onClick={() => setView(mode)}
                  >
                    {mode === 'diff' ? 'Diff' : 'Full file'}
                  </button>
                ))}
              </div>
            )}
          </span>
        </div>

        <CodeScroll
          file={activeFile}
          diff={diff}
          mode={effectiveView}
          issues={result.issues}
          focusLine={focusLine}
          onIssueFocusHandled={onIssueFocusHandled}
        />
      </div>
    </div>
  );
}

interface CodeScrollProps {
  file: FileSummary | undefined;
  diff: FileDiff | undefined;
  mode: ViewMode;
  issues: Issue[];
  focusLine: number | null;
  onIssueFocusHandled: () => void;
}

function CodeScroll({ file, diff, mode, issues, focusLine, onIssueFocusHandled }: CodeScrollProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileIssues = useMemo(
    () => (file ? issues.filter((i) => i.file === file.path && typeof i.line === 'number') : []),
    [issues, file],
  );
  const marked = useMemo(() => new Set(fileIssues.map((i) => i.line as number)), [fileIssues]);

  useEffect(() => {
    if (focusLine == null) return;
    const el = scrollRef.current?.querySelector(`[data-line="${focusLine}"]`);
    if (el) {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      onIssueFocusHandled();
    }
  }, [focusLine, mode, file?.path, onIssueFocusHandled]);

  if (file?.skipped) {
    return (
      <div className="code-empty">
        File skipped: {file.skip_reason ?? 'not reviewable'}
      </div>
    );
  }

  if (mode === 'diff' && diff) {
    return (
      <div className="code-scroll" ref={scrollRef}>
        <table className="code-table">
          <tbody>
            {diff.hunks.map((hunk, hunkIndex) => (
              <HunkRows
                key={hunkIndex}
                hunk={hunk}
                marked={marked}
                focusLine={focusLine}
              />
            ))}
          </tbody>
        </table>
        {file?.truncated && (
          <p className="skipped-note">Full file view truncated for large files.</p>
        )}
      </div>
    );
  }

  const content = file?.content ?? '';
  if (!content) {
    return <div className="code-empty">No content available for this file.</div>;
  }

  const lines = content.split('\n');
  return (
    <div className="code-scroll" ref={scrollRef}>
      <table className="code-table">
        <tbody>
          {lines.map((text, index) => {
            const lineNo = index + 1;
            const isMarked = marked.has(lineNo);
            const isFocus = focusLine === lineNo;
            return (
              <tr
                key={lineNo}
                data-line={lineNo}
                className={`code-row ${isFocus ? 'flash' : ''}`.trim()}
              >
                <td className={`code-gutter ${isMarked ? 'marker' : ''}`.trim()}>{lineNo}</td>
                <td className={`code-line ${isMarked ? 'marked' : ''}`.trim()}>{text || ' '}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {file?.truncated && <p className="skipped-note">File content truncated for display.</p>}
    </div>
  );
}

interface HunkRowsProps {
  hunk: {
    header: string | null;
    lines: DiffLine[];
  };
  marked: Set<number>;
  focusLine: number | null;
}

function HunkRows({ hunk, marked, focusLine }: HunkRowsProps) {
  return (
    <>
      <tr className="diff-hunk-row">
        <td className="code-gutter" colSpan={2}>
          {hunk.header ?? '@@'}
        </td>
      </tr>
      {hunk.lines.map((line, index) => {
        const lineNo = line.new_no;
        const isMarked = lineNo != null && marked.has(lineNo);
        const isFocus = lineNo != null && focusLine === lineNo;
        const sign = line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' ';
        return (
          <tr
            key={index}
            data-line={lineNo ?? undefined}
            className={`code-row ${isFocus ? 'flash' : ''}`.trim()}
          >
            <td className={`code-gutter ${isMarked ? 'marker' : ''}`.trim()}>
              {line.type === 'del' ? (line.old_no ?? '') : (line.new_no ?? '')}
            </td>
            <td className={`code-line ${line.type} ${isMarked ? 'marked' : ''}`.trim()}>
              <span className="diff-sign">{sign}</span>
              {line.text || ' '}
            </td>
          </tr>
        );
      })}
    </>
  );
}
