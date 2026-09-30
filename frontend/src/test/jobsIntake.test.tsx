import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import { SourceIntake } from '../components/SourceIntake';
import {
  ApiRequestError,
  createJob,
  uploadJob,
  getJob,
  cancelJob,
  listBranches,
} from '../services/api';

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

const HEALTHY = { status: 'healthy', service: 'prism-api' };

describe('job api layer', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('createJob posts JSON to /api/jobs', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'j1', status: 'queued' }));

    await createJob({ mode: 'paste', code: 'print(1)' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/jobs');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ mode: 'paste', code: 'print(1)' });
  });

  it('uploadJob posts multipart with relative paths as filenames', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'j2', status: 'queued' }));

    const file = new File(['print(1)'], 'app.py', { type: 'text/x-python' });
    await uploadJob(
      [
        { file, path: 'src/app.py' },
        { file: new File(['x'], 'b.js') },
      ],
      'security',
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/jobs/upload');
    expect(init.method).toBe('POST');
    // No explicit Content-Type: the browser must add the multipart boundary.
    expect(init.headers).toBeUndefined();

    const form = init.body as FormData;
    expect((form.get('files') as File).name).toBe('src/app.py');
    expect(form.getAll('files')).toHaveLength(2);
    expect(form.get('query')).toBe('security');
  });

  it('getJob and cancelJob address the job by encoded id', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ id: 'j 3', status: 'queued' })));

    await getJob('j 3');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/jobs/j%203');

    await cancelJob('j 3');
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe('/api/jobs/j%203');
    expect(init.method).toBe('DELETE');
  });

  it('listBranches queries /api/branches with the encoded repo url', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ branches: [{ name: 'main', is_default: true, is_head: true }] }),
    );

    await listBranches('https://x.test/a b.git');

    const [url] = fetchMock.mock.calls[0];
    const expected = new URLSearchParams({ repo_url: 'https://x.test/a b.git' }).toString();
    expect(url).toBe(`/api/branches?${expected}`);
  });

  it('surfaces HTTP errors as ApiRequestError with the backend detail', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Repository not found' }), { status: 400 }),
    );

    const error = await createJob({ mode: 'branch', repo_url: 'x', branch: 'b' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error.kind).toBe('http');
    expect(error.message).toBe('Repository not found');
  });
});

describe('source intake picker', () => {
  const noop = () => {};

  function renderIntake() {
    return render(
      <SourceIntake
        disabled={false}
        onSubmitPaste={noop}
        onSubmitFiles={noop}
        onSubmitBranch={noop}
      />,
    );
  }

  it('offers three equal mode cards plus a secondary paste shortcut', () => {
    renderIntake();

    for (const name of ['Review files', 'Review folder', 'Review branch']) {
      const card = screen.getByRole('button', { name: new RegExp(name, 'i') });
      expect(card).toBeInTheDocument();
      expect(card.closest('.mode-grid')).not.toBeNull();
    }

    expect(
      screen.getByRole('button', { name: /paste a code snippet/i }),
    ).toBeInTheDocument();
    // No form is visible until a mode is chosen.
    expect(screen.queryByRole('button', { name: 'Change source' })).not.toBeInTheDocument();
  });

  it('opens the files dropzone when the files card is chosen', () => {
    renderIntake();

    fireEvent.click(screen.getByRole('button', { name: /review files/i }));

    expect(screen.getByText('Drop files here or click to browse')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change source' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review Files' })).toBeDisabled();
    expect(screen.getByLabelText('Specific review focus (optional)')).toBeInTheDocument();
  });

  it('opens the folder picker when the folder card is chosen', () => {
    renderIntake();

    fireEvent.click(screen.getByRole('button', { name: /review folder/i }));

    expect(screen.getByText('Drop a folder here or click to browse')).toBeInTheDocument();
    expect(screen.getByLabelText('Specific review focus (optional)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review Folder' })).toBeDisabled();
  });

  it('reveals branch inputs and requires url + branch before submit', () => {
    renderIntake();

    fireEvent.click(screen.getByRole('button', { name: /review branch/i }));

    expect(screen.getByLabelText('Repository URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Base branch (diff against)')).toBeInTheDocument();

    const submit = screen.getByRole('button', { name: 'Review Branch' });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Repository URL'), {
      target: { value: 'https://github.com/owner/repo.git' },
    });
    fireEvent.change(screen.getByLabelText('Branch'), { target: { value: 'feature' } });
    expect(submit).toBeEnabled();
  });

  it('returns to the picker via the back button', () => {
    renderIntake();

    fireEvent.click(screen.getByRole('button', { name: /review branch/i }));
    expect(screen.getByLabelText('Repository URL')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /change source/i }));

    expect(screen.queryByLabelText('Repository URL')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /review files/i })).toBeInTheDocument();
  });
});

describe('requirements intake', () => {
  const onSubmitPaste = vi.fn();
  const onSubmitFiles = vi.fn();
  const onSubmitBranch = vi.fn();

  function renderRequirementsIntake() {
    return render(
      <SourceIntake
        disabled={false}
        onSubmitPaste={onSubmitPaste}
        onSubmitFiles={onSubmitFiles}
        onSubmitBranch={onSubmitBranch}
      />,
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers a requirements card that opens the requirements form', () => {
    renderRequirementsIntake();

    const card = screen.getByRole('button', { name: /check requirements/i });
    expect(card).toBeInTheDocument();
    expect(card.closest('.mode-grid')).not.toBeNull();

    fireEvent.click(card);

    expect(screen.getByLabelText('Requirements')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/one requirement per line/i)).toBeInTheDocument();
    expect(screen.getByText(/paste issues, work items/i)).toBeInTheDocument();
    expect(screen.getByText(/choose where the code/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change source' })).toBeInTheDocument();
  });

  it('lists the four code sources as pills once requirements are chosen', () => {
    renderRequirementsIntake();
    fireEvent.click(screen.getByRole('button', { name: /check requirements/i }));

    for (const label of ['Files', 'Folder', 'Paste code', 'Branch']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('blocks the branch submit until requirements text is provided', () => {
    renderRequirementsIntake();
    fireEvent.click(screen.getByRole('button', { name: /check requirements/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Branch' }));

    fireEvent.change(screen.getByLabelText('Repository URL'), {
      target: { value: 'https://github.com/o/r.git' },
    });
    fireEvent.change(screen.getByLabelText('Branch'), { target: { value: 'feature' } });

    const submit = screen.getByRole('button', { name: 'Review Branch' });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Requirements'), {
      target: { value: '#1 reset link expires' },
    });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmitBranch).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'requirements',
        repo_url: 'https://github.com/o/r.git',
        branch: 'feature',
        requirements: '#1 reset link expires',
      }),
    );
  });

  it('passes requirements through the paste source and leaves plain paste untouched', () => {
    renderRequirementsIntake();

    fireEvent.click(screen.getByRole('button', { name: /paste a code snippet/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Review Code' }));
    expect(onSubmitPaste).toHaveBeenCalledTimes(1);
    expect(onSubmitPaste.mock.calls[0][1]).toBeUndefined();

    fireEvent.click(screen.getByRole('button', { name: /change source/i }));
    fireEvent.click(screen.getByRole('button', { name: /check requirements/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Paste code' }));

    const submit = screen.getByRole('button', { name: 'Check Requirements' });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Requirements'), {
      target: { value: 'US-3 export CSV' },
    });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmitPaste).toHaveBeenCalledTimes(2);
    expect(onSubmitPaste.mock.calls[1][1]).toBe('US-3 export CSV');
  });

  it('returns to the picker from the requirements form', () => {
    renderRequirementsIntake();

    fireEvent.click(screen.getByRole('button', { name: /check requirements/i }));
    expect(screen.getByLabelText('Requirements')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /change source/i }));

    expect(screen.queryByLabelText('Requirements')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /review files/i })).toBeInTheDocument();
  });
});

describe('theme', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    fetchMock = vi.fn().mockResolvedValue(jsonResponse(HEALTHY));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete document.documentElement.dataset.theme;
  });

  it('defaults to dark, toggles to light, and persists the choice', async () => {
    render(<App />);

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('dark');
    });

    fireEvent.click(screen.getByRole('button', { name: /switch to light theme/i }));

    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('prism-theme')).toBe('light');
    expect(screen.getByRole('button', { name: /switch to dark theme/i })).toBeInTheDocument();
  });

  it('restores the persisted theme on mount', async () => {
    localStorage.setItem('prism-theme', 'light');

    render(<App />);

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('light');
    });
  });
});
