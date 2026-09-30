import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RequirementsPanel } from '../components/RequirementsPanel';
import { ProgressView } from '../components/ProgressView';
import type { RequirementsReport } from '../types/review';
import type { JobResponse, SourceMode } from '../types/job';

const report: RequirementsReport = {
  items: [
    {
      id: '#12',
      title: 'Reset-password link expires after 15 minutes',
      kind: 'story',
      status: 'implemented',
      evidence: ['src/auth/reset.py:42'],
      gaps: '',
      notes: null,
    },
    {
      id: 'US-3',
      title: 'Export reports to CSV',
      kind: 'story',
      status: 'partial',
      evidence: ['src/reports/export.py:10', 'covered by design doc'],
      gaps: 'No streaming for large exports',
      notes: 'CSV writer exists but is unbounded',
    },
    {
      id: 'BUG-88',
      title: 'Checkout fails on empty cart',
      kind: 'bug',
      status: 'missing',
      evidence: [],
      gaps: 'No guard found in cart code',
      notes: null,
    },
  ],
  summary: 'Two of three requirements have some coverage.',
  implemented: 1,
  partial: 1,
  missing: 1,
  coverage_pct: 33,
};

describe('RequirementsPanel', () => {
  it('shows coverage percentage, totals and the summary', () => {
    render(<RequirementsPanel report={report} />);

    expect(screen.getByText('Requirements (3)')).toBeInTheDocument();
    expect(screen.getByText('33% covered')).toBeInTheDocument();
    expect(screen.getByText('implemented')).toBeInTheDocument();
    expect(screen.getByText('partial')).toBeInTheDocument();
    expect(screen.getByText('missing')).toBeInTheDocument();
    expect(screen.getByText('Two of three requirements have some coverage.')).toBeInTheDocument();
  });

  it('renders each requirement with its status, id, title and kind', () => {
    render(<RequirementsPanel report={report} />);

    expect(screen.getByText('Implemented')).toBeInTheDocument();
    expect(screen.getByText('Partial')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();

    expect(screen.getByText('#12')).toBeInTheDocument();
    expect(screen.getByText('Reset-password link expires after 15 minutes')).toBeInTheDocument();
    expect(screen.getByText('Export reports to CSV')).toBeInTheDocument();
    expect(screen.getByText('BUG-88')).toBeInTheDocument();
    expect(screen.getByText('bug')).toBeInTheDocument();
    expect(screen.getAllByText('story')).toHaveLength(2);
  });

  it('shows gaps when a requirement is not fully covered', () => {
    render(<RequirementsPanel report={report} />);

    expect(screen.getByText(/No streaming for large exports/)).toBeInTheDocument();
    expect(screen.getByText(/No guard found in cart code/)).toBeInTheDocument();
  });

  it('jumps to the evidence location when a path:line button is clicked', () => {
    const onSelect = vi.fn();
    render(<RequirementsPanel report={report} onSelect={onSelect} />);

    const button = screen.getByRole('button', { name: 'src/auth/reset.py:42' });
    fireEvent.click(button);
    expect(onSelect).toHaveBeenCalledWith('src/auth/reset.py', 42);
  });

  it('renders free-form evidence as text instead of a button', () => {
    const onSelect = vi.fn();
    render(<RequirementsPanel report={report} onSelect={onSelect} />);

    expect(screen.getByText('covered by design doc')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'covered by design doc' }),
    ).not.toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows an empty state when no requirements were matched', () => {
    render(
      <RequirementsPanel report={{ ...report, items: [], coverage_pct: 0 }} />,
    );

    expect(screen.getByText(/No requirements were matched/i)).toBeInTheDocument();
  });
});

function makeJob(mode: SourceMode, step: string): JobResponse {
  return {
    job_id: 'j1',
    status: 'reviewing',
    progress: { step, current: 0, total: 0, current_file: null },
    result: null,
    error: null,
    mode,
    skipped: [],
  };
}

describe('ProgressView requirements step', () => {
  it('adds a checking requirements step for requirements jobs', () => {
    render(
      <ProgressView
        job={makeJob('requirements', 'checking requirements')}
        onCancel={vi.fn()}
        cancelling={false}
      />,
    );

    expect(screen.getByText('Checking requirements')).toBeInTheDocument();
    expect(screen.getByText('Reviewing files')).toBeInTheDocument();
    expect(document.querySelectorAll('.progress-step')).toHaveLength(5);
  });

  it('keeps the original four steps for other modes', () => {
    render(
      <ProgressView job={makeJob('files', 'reviewing')} onCancel={vi.fn()} cancelling={false} />,
    );

    expect(screen.queryByText('Checking requirements')).not.toBeInTheDocument();
    expect(screen.getByText('Reviewing files')).toBeInTheDocument();
    expect(document.querySelectorAll('.progress-step')).toHaveLength(4);
  });
});
