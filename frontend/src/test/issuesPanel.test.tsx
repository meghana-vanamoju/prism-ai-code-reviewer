import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IssuesPanel } from '../components/IssuesPanel';
import type { Issue } from '../types/review';

/**
 * Regression coverage for the IssuesPanel empty state.
 *
 * An empty issues array only means PRISM surfaced nothing that requires a
 * change. The previous copy ("No issues found — code looks good!") overstated
 * that as an endorsement of the code, which is wrong when the review summary
 * still flags an observation or records a remembered team decision that means
 * no change is needed.
 */

const SAMPLE_ISSUE: Issue = {
  severity: 'high',
  title: 'Floating-point arithmetic used for money',
  description: 'Monetary values must not use JavaScript numbers.',
  recommendation: 'Switch to Decimal.',
  memory_reference: '[2]',
};

describe('IssuesPanel empty state', () => {
  it('does not claim the code is good', () => {
    render(<IssuesPanel issues={[]} />);

    // The old wording made a quality claim the empty array cannot support.
    expect(screen.queryByText(/code looks good/i)).not.toBeInTheDocument();
  });

  it('states that no actionable issues were found', () => {
    render(<IssuesPanel issues={[]} />);

    expect(screen.getByText('No actionable issues found')).toBeInTheDocument();
  });

  it('explains that nothing was found against standards and remembered decisions', () => {
    render(<IssuesPanel issues={[]} />);

    expect(
      screen.getByText(
        'PRISM found no issues requiring changes based on the current team standards and remembered decisions.',
      ),
    ).toBeInTheDocument();
  });

  it('keeps the checkmark icon in the empty state', () => {
    const { container } = render(<IssuesPanel issues={[]} />);

    expect(container.querySelector('.empty-state .check-icon')).toBeInTheDocument();
  });

  it('shows the empty state instead of issue cards when there are no issues', () => {
    const { container } = render(<IssuesPanel issues={[]} />);

    expect(container.querySelector('.issues-panel.empty')).toBeInTheDocument();
    expect(container.querySelector('.issue-card')).not.toBeInTheDocument();
    expect(screen.queryByText(/Issues Found/)).not.toBeInTheDocument();
  });
});

describe('IssuesPanel with issues', () => {
  it('renders issue cards and no empty-state copy', () => {
    render(<IssuesPanel issues={[SAMPLE_ISSUE]} />);

    expect(screen.getByText('Issues Found (1)')).toBeInTheDocument();
    expect(screen.getByText(SAMPLE_ISSUE.title)).toBeInTheDocument();
    expect(screen.queryByText('No actionable issues found')).not.toBeInTheDocument();
  });

  it('does not render the empty-state explanation when issues are present', () => {
    const { container } = render(<IssuesPanel issues={[SAMPLE_ISSUE]} />);

    expect(container.querySelector('.empty-hint')).not.toBeInTheDocument();
    expect(container.querySelector('.empty-state')).not.toBeInTheDocument();
  });
});
