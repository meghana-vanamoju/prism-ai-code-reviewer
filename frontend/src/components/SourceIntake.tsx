import { useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { CodeEditor } from './CodeEditor';
import { listBranches } from '../services/api';
import type { UploadEntry } from '../services/api';
import type { BranchInfo, JobRequest } from '../types/job';
import type { ReviewRequest } from '../types/review';

export type SourceTab = 'paste' | 'files' | 'folder' | 'branch' | 'requirements';
export type CodeSourceTab = Exclude<SourceTab, 'requirements'>;

interface SourceIntakeProps {
  disabled: boolean;
  onSubmitPaste: (request: ReviewRequest, requirements?: string) => void;
  onSubmitFiles: (entries: UploadEntry[], query: string, requirements?: string) => void;
  onSubmitBranch: (request: JobRequest) => void;
}

interface ModeCard {
  id: CodeSourceTab | 'requirements';
  title: string;
  desc: string;
  meta: string;
}

const MODES: ModeCard[] = [
  {
    id: 'files',
    title: 'Review files',
    desc: 'Drop individual source files. Binaries, lockfiles and generated code are filtered out.',
    meta: 'Multi-select · any language',
  },
  {
    id: 'folder',
    title: 'Review folder',
    desc: 'Scan a whole directory with its structure preserved, path by path.',
    meta: 'Recursive · ignored dirs skipped',
  },
  {
    id: 'branch',
    title: 'Review branch',
    desc: 'Diff a branch against its base on any reachable Git remote.',
    meta: 'GitHub · GitLab · self-hosted',
  },
  {
    id: 'requirements',
    title: 'Check requirements',
    desc: 'Map issues, work items, user stories and bug fixes onto the code and see what is covered.',
    meta: 'Coverage · evidence · gaps',
  },
];

const MODE_LABEL: Record<SourceTab, string> = {
  paste: 'Paste snippet',
  files: 'File upload',
  folder: 'Folder scan',
  branch: 'Branch diff',
  requirements: 'Requirements check',
};

const REQ_SOURCES: { id: CodeSourceTab; label: string }[] = [
  { id: 'files', label: 'Files' },
  { id: 'folder', label: 'Folder' },
  { id: 'paste', label: 'Paste code' },
  { id: 'branch', label: 'Branch' },
];

const DEFAULT_SAMPLE = `function calculateTotal(items) {
  let total = 0;
  for (const item of items) {
    total += item.price;
  }
  return total;
}`;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function baseName(path: string): string {
  const i = path.lastIndexOf('/');
  return i === -1 ? path : path.slice(i + 1);
}

function dirName(path: string): string {
  const i = path.lastIndexOf('/');
  return i === -1 ? '' : path.slice(0, i);
}

function extensionOf(path: string): string {
  const name = baseName(path);
  const i = name.lastIndexOf('.');
  return i <= 0 ? '' : name.slice(i + 1).toLowerCase();
}

function entryPath(entry: UploadEntry): string {
  return entry.path ?? entry.file.name;
}

interface FileRowProps {
  entry: UploadEntry;
  onRemove: (path: string) => void;
}

function FileRow({ entry, onRemove }: FileRowProps) {
  const path = entryPath(entry);
  const ext = extensionOf(path);
  return (
    <li className="file-row">
      <span className={`file-ext ${ext ? '' : 'none'}`.trim()}>{ext || 'txt'}</span>
      <span className="file-row-name">{path}</span>
      <span className="file-row-size">{formatSize(entry.file.size)}</span>
      <button
        type="button"
        className="file-row-remove"
        aria-label={`Remove ${path}`}
        onClick={() => onRemove(path)}
      >
        ×
      </button>
    </li>
  );
}

export function SourceIntake({
  disabled,
  onSubmitPaste,
  onSubmitFiles,
  onSubmitBranch,
}: SourceIntakeProps) {
  const [tab, setTab] = useState<SourceTab | null>(null);

  const [files, setFiles] = useState<UploadEntry[]>([]);
  const [folderQuery, setFolderQuery] = useState('');
  const [dragover, setDragover] = useState(false);

  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('');
  const [baseBranch, setBaseBranch] = useState('');
  const [branchQuery, setBranchQuery] = useState('');
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [branchStatus, setBranchStatus] = useState<string | null>(null);
  const [branchError, setBranchError] = useState<string | null>(null);
  const [listing, setListing] = useState(false);

  const [reqText, setReqText] = useState('');
  const [reqSource, setReqSource] = useState<CodeSourceTab | null>(null);

  const filesInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const isRequirements = tab === 'requirements';

  const totalBytes = useMemo(() => files.reduce((sum, f) => sum + f.file.size, 0), [files]);

  const fileGroups = useMemo(() => {
    const map = new Map<string, UploadEntry[]>();
    for (const entry of files) {
      const dir = dirName(entryPath(entry));
      const bucket = map.get(dir);
      if (bucket) bucket.push(entry);
      else map.set(dir, [entry]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [files]);

  const collectEntries = (list: FileList | null, useRelative: boolean): UploadEntry[] => {
    if (!list) return [];
    const entries: UploadEntry[] = [];
    for (const file of Array.from(list)) {
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
      const path = useRelative && relative ? relative : file.name;
      entries.push({ file, path });
    }
    return entries;
  };

  const handleFilesInput = (input: HTMLInputElement | null, useRelative: boolean) => {
    setFiles(collectEntries(input?.files ?? null, useRelative));
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragover(false);
    if (disabled) return;
    // DataTransfer files carry no folder structure, so they land at root.
    setFiles(collectEntries(e.dataTransfer.files, false));
  };

  const removeFile = (path: string) => {
    setFiles((prev) => prev.filter((entry) => entryPath(entry) !== path));
  };

  const handleListBranches = async () => {
    const url = repoUrl.trim();
    if (!url) return;
    setListing(true);
    setBranchError(null);
    setBranchStatus(null);
    try {
      const res = await listBranches(url);
      setBranches(res.branches);
      const def = res.branches.find((b) => b.is_default);
      if (def) {
        setBranch((prev) => prev || def.name);
        setBaseBranch((prev) => prev || def.name);
      }
      setBranchStatus(`${res.branches.length} branches found`);
    } catch (err) {
      setBranchError(err instanceof Error ? err.message : 'Failed to list branches');
      setBranches([]);
    } finally {
      setListing(false);
    }
  };

  const requirementsReady = !isRequirements || reqText.trim().length > 0;

  const submitBranch = () => {
    if (!repoUrl.trim() || !branch.trim() || !requirementsReady) return;
    const requirements = isRequirements ? reqText.trim() : '';
    onSubmitBranch({
      mode: isRequirements ? 'requirements' : 'branch',
      repo_url: repoUrl.trim(),
      branch: branch.trim(),
      base_branch: baseBranch.trim() || undefined,
      query: branchQuery.trim() || undefined,
      requirements: requirements || undefined,
    });
  };

  const submitFiles = (query: string) => {
    if (files.length === 0 || !requirementsReady) return;
    const requirements = isRequirements ? reqText.trim() : '';
    onSubmitFiles(files, query, requirements || undefined);
  };

  const handlePasteSubmit = (request: ReviewRequest) => {
    if (!requirementsReady) return;
    const requirements = isRequirements ? reqText.trim() : '';
    onSubmitPaste(request, requirements || undefined);
  };

  const openMode = (id: SourceTab) => {
    if (disabled) return;
    setTab(id);
    setDragover(false);
  };

  const openReqSource = (source: CodeSourceTab) => {
    if (disabled) return;
    setReqSource(source);
    setDragover(false);
  };

  const renderCodeSource = (source: CodeSourceTab) => {
    if (source === 'paste') {
      return (
        <CodeEditor
          onSubmit={handlePasteSubmit}
          isLoading={disabled}
          defaultCode={DEFAULT_SAMPLE}
          disabled={!requirementsReady}
          submitLabel={isRequirements ? 'Check Requirements' : undefined}
        />
      );
    }

    if (source === 'files') {
      return (
        <div>
          <div
            className={`dropzone ${dragover ? 'dragover' : ''}`.trim()}
            onClick={() => filesInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragover(true);
            }}
            onDragLeave={() => setDragover(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') filesInputRef.current?.click();
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 16V4m0 0L7 9m5-5 5 5" />
              <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
            </svg>
            <p className="dropzone-title">
              {files.length > 0
                ? `${files.length} file${files.length === 1 ? '' : 's'} selected`
                : 'Drop files here or click to browse'}
            </p>
            <p className="dropzone-hint">
              Source files only — binaries, lockfiles and docs are skipped
            </p>
            <input
              ref={filesInputRef}
              type="file"
              multiple
              disabled={disabled}
              onChange={(e) => handleFilesInput(e.target, false)}
            />
          </div>

          {files.length > 0 && (
            <>
              <div className="selection-summary">
                <span>
                  {files.length} file{files.length === 1 ? '' : 's'}
                </span>
                <span>{formatSize(totalBytes)}</span>
              </div>
              <ul className="file-rows">
                {files.slice(0, 60).map((entry) => (
                  <FileRow key={entryPath(entry)} entry={entry} onRemove={removeFile} />
                ))}
                {files.length > 60 && (
                  <li className="file-row file-row-more">
                    +{files.length - 60} more files
                  </li>
                )}
              </ul>
            </>
          )}

          <FilesQueryRow
            onSubmit={submitFiles}
            disabled={disabled || files.length === 0 || !requirementsReady}
            hasFiles={files.length > 0}
          />
        </div>
      );
    }

    if (source === 'folder') {
      return (
        <div>
          <div
            className={`dropzone ${dragover ? 'dragover' : ''}`.trim()}
            onClick={() => folderInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragover(true);
            }}
            onDragLeave={() => setDragover(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') folderInputRef.current?.click();
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
            </svg>
            <p className="dropzone-title">
              {files.length > 0
                ? `${files.length} file${files.length === 1 ? '' : 's'} in selection`
                : 'Drop a folder here or click to browse'}
            </p>
            <p className="dropzone-hint">
              Structure is preserved; ignored directories are skipped
            </p>
            <input
              ref={folderInputRef}
              type="file"
              multiple
              // Non-standard but universally supported directory picker attrs.
              {...{ webkitdirectory: '', directory: '' }}
              disabled={disabled}
              onChange={(e) => handleFilesInput(e.target, true)}
            />
          </div>

          {files.length > 0 && (
            <>
              <div className="selection-summary">
                <span>
                  {files.length} file{files.length === 1 ? '' : 's'} ·{' '}
                  {fileGroups.length} folder{fileGroups.length === 1 ? '' : 's'}
                </span>
                <span>{formatSize(totalBytes)}</span>
              </div>
              <div className="tree">
                {fileGroups.map(([dir, entries]) => (
                  <div className="tree-group" key={dir || 'root'}>
                    <div className="tree-dir">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                      </svg>
                      <span className="tree-dir-name">{dir || 'root'}</span>
                      <span className="tree-dir-count">{entries.length}</span>
                    </div>
                    <ul className="file-rows tree-files">
                      {entries.slice(0, 40).map((entry) => (
                        <FileRow key={entryPath(entry)} entry={entry} onRemove={removeFile} />
                      ))}
                      {entries.length > 40 && (
                        <li className="file-row file-row-more">
                          +{entries.length - 40} more in this folder
                        </li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="review-options" style={{ marginTop: 14 }}>
            <div className="query-input">
              <label htmlFor="folder-query">Specific review focus (optional)</label>
              <input
                id="folder-query"
                type="text"
                value={folderQuery}
                onChange={(e) => setFolderQuery(e.target.value)}
                placeholder="e.g. security, error handling, test coverage"
              />
            </div>
            <button
              type="button"
              className="review-button"
              disabled={disabled || files.length === 0 || !requirementsReady}
              onClick={() => submitFiles(folderQuery.trim())}
            >
              Review Folder
            </button>
          </div>
        </div>
      );
    }

    // branch
    return (
      <div className="branch-form">
        <p className="source-hint">
          Paste a public repository URL (https or git@). PRISM shallow-clones the branch
          and reviews its diff against the base branch.
        </p>

        <div className="branch-field">
          <label htmlFor="repo-url">Repository URL</label>
          <div className="input-with-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M12 3a9 9 0 0 0-2.8 17.5c.45.08.6-.2.6-.44v-1.6c-2.5.54-3-1.2-3-1.2-.4-1.05-1-1.33-1-1.33-.83-.57.06-.56.06-.56.92.06 1.4.95 1.4.95.82 1.4 2.15 1 2.68.76.08-.6.32-1 .58-1.23-2-.23-4.1-1-4.1-4.45 0-.98.35-1.78.93-2.4-.1-.24-.4-1.16.08-2.4 0 0 .76-.25 2.48.92a8.6 8.6 0 0 1 4.5 0c1.72-1.17 2.47-.92 2.47-.92.5 1.24.19 2.16.1 2.4.58.62.92 1.42.92 2.4 0 3.47-2.1 4.22-4.11 4.45.32.28.61.83.61 1.68v2.48c0 .24.16.53.62.44A9 9 0 0 0 12 3z" />
            </svg>
            <input
              id="repo-url"
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo.git"
              disabled={disabled}
            />
          </div>
        </div>

        <div className="branch-actions">
          <button
            type="button"
            className="review-button secondary"
            onClick={handleListBranches}
            disabled={disabled || listing || !repoUrl.trim()}
          >
            {listing ? 'Listing…' : 'List branches'}
          </button>
          {branchStatus && <span className="branch-status">{branchStatus}</span>}
          {branchError && <span className="branch-error">{branchError}</span>}
        </div>

        {branches.length > 0 && (
          <div className="branch-chips">
            {branches.map((b) => (
              <button
                key={b.name}
                type="button"
                className={`branch-chip ${branch === b.name ? 'selected' : ''}`.trim()}
                onClick={() => setBranch(b.name)}
                title={b.is_default ? 'Default branch' : undefined}
              >
                {b.name}
                {b.is_default && <span className="default-star">★</span>}
              </button>
            ))}
          </div>
        )}

        <div className="branch-field-row">
          <div className="branch-field">
            <label htmlFor="branch-name">Branch</label>
            <input
              id="branch-name"
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              disabled={disabled}
            />
          </div>
          <div className="branch-field">
            <label htmlFor="base-branch">Base branch (diff against)</label>
            <input
              id="base-branch"
              type="text"
              value={baseBranch}
              onChange={(e) => setBaseBranch(e.target.value)}
              placeholder="defaults to branch's default"
              disabled={disabled}
            />
          </div>
        </div>

        <div className="branch-field">
          <label htmlFor="branch-query">Specific review focus (optional)</label>
          <input
            id="branch-query"
            type="text"
            value={branchQuery}
            onChange={(e) => setBranchQuery(e.target.value)}
            placeholder="e.g. API contract changes, auth logic"
          />
        </div>

        <div className="branch-actions">
          <button
            type="button"
            className="review-button"
            onClick={submitBranch}
            disabled={
              disabled || !repoUrl.trim() || !branch.trim() || !requirementsReady
            }
          >
            Review Branch
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="source-panel">
      {tab === null && (
        <div className="mode-picker">
          <div className="mode-picker-head">
            <span className="panel-eyebrow">Review source</span>
            <p>Pick how the code reaches PRISM.</p>
          </div>

          <div className="mode-grid">
            {MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                className="mode-card"
                onClick={() => openMode(mode.id)}
                disabled={disabled}
              >
                <span className={`mode-icon mode-icon-${mode.id}`} aria-hidden="true">
                  {mode.id === 'files' && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" strokeLinecap="round" />
                      <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" strokeLinecap="round" />
                    </svg>
                  )}
                  {mode.id === 'folder' && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2h9A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-10z" />
                    </svg>
                  )}
                  {mode.id === 'branch' && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <circle cx="6" cy="6" r="2.2" />
                      <circle cx="6" cy="18" r="2.2" />
                      <circle cx="18" cy="8" r="2.2" />
                      <path d="M6 8.2v7.6M8.2 6.6c4 .6 6.5 1.6 7.6 3.1" strokeLinecap="round" />
                    </svg>
                  )}
                  {mode.id === 'requirements' && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M8 4H6.5A1.5 1.5 0 0 0 5 5.5v14A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V5.5A1.5 1.5 0 0 0 17.5 4H16" strokeLinecap="round" />
                      <rect x="8" y="2.5" width="8" height="3.5" rx="1.2" />
                      <path d="M8.5 11l1.6 1.6 3.2-3.4M8.5 16l1.6 1.6 3.2-3.4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="mode-title">{mode.title}</span>
                <span className="mode-desc">{mode.desc}</span>
                <span className="mode-meta">{mode.meta}</span>
                <span className="mode-arrow" aria-hidden="true">
                  →
                </span>
              </button>
            ))}
          </div>

          <button type="button" className="mode-secondary" onClick={() => openMode('paste')} disabled={disabled}>
            Or paste a code snippet instead
          </button>
        </div>
      )}

      {tab !== null && (
        <div className="source-form">
          <div className="form-topbar">
            <button
              type="button"
              className="back-btn"
              onClick={() => setTab(null)}
              disabled={disabled}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Change source
            </button>
            <span className="form-mode">{MODE_LABEL[tab]}</span>
          </div>

          <div className="source-body">
            {tab === 'paste' && renderCodeSource('paste')}
            {tab === 'files' && renderCodeSource('files')}
            {tab === 'folder' && renderCodeSource('folder')}
            {tab === 'branch' && renderCodeSource('branch')}

            {tab === 'requirements' && (
              <div className="requirements-form">
                <div className="requirements-input">
                  <label htmlFor="requirements-text">Requirements</label>
                  <textarea
                    id="requirements-text"
                    value={reqText}
                    onChange={(e) => setReqText(e.target.value)}
                    rows={7}
                    disabled={disabled}
                    placeholder={
                      'One requirement per line, e.g.\n#12 Reset-password link must expire after 15 minutes\nUS-3 As a user I can export reports to CSV\nBUG-88 Checkout fails when the cart is empty'
                    }
                    aria-describedby="requirements-hint"
                  />
                  <p className="requirements-hint" id="requirements-hint">
                    Paste issues, work items, user stories or bug fixes — one per line. PRISM maps
                    each to the code and reports implemented, partial or missing.
                  </p>
                </div>

                <div className="req-source">
                  <span className="req-source-label">Check against</span>
                  <div className="req-source-pills">
                    {REQ_SOURCES.map((source) => (
                      <button
                        key={source.id}
                        type="button"
                        className={`req-source-pill ${reqSource === source.id ? 'active' : ''}`.trim()}
                        onClick={() => openReqSource(source.id)}
                        disabled={disabled}
                        aria-pressed={reqSource === source.id}
                      >
                        {source.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="req-source-body">
                  {reqSource === null ? (
                    <p className="req-source-hint">
                      Choose where the code to check against those requirements comes from.
                    </p>
                  ) : (
                    renderCodeSource(reqSource)
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface FilesQueryRowProps {
  onSubmit: (query: string) => void;
  disabled: boolean;
  hasFiles: boolean;
}

function FilesQueryRow({ onSubmit, disabled, hasFiles }: FilesQueryRowProps) {
  const [query, setQuery] = useState('');
  return (
    <div className="review-options" style={{ marginTop: 14 }}>
      <div className="query-input">
        <label htmlFor="files-query">Specific review focus (optional)</label>
        <input
          id="files-query"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. security, error handling, performance"
        />
      </div>
      <button
        type="button"
        className="review-button"
        disabled={disabled || !hasFiles}
        onClick={() => onSubmit(query.trim())}
      >
        Review Files
      </button>
    </div>
  );
}
