import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LocalModelWizard } from './LocalModelWizard';
import { RuntimeLimitsSection } from './RuntimeLimitsSection';
import { CostComparison } from '../Dashboard/CostComparison';

describe('Advanced Runtime & Local Model Components', () => {
  it('renders LocalModelWizard initial scan step', () => {
    const html = renderToStaticMarkup(<LocalModelWizard />);
    expect(html).toContain('One-Click Local Model Recommendation');
    expect(html).toContain('Scan Hardware &amp; Recommend');
    expect(html).toContain('System Hardware Discovery');
  });

  it('renders RuntimeLimitsSection container', () => {
    const html = renderToStaticMarkup(<RuntimeLimitsSection />);
    expect(html).toContain('Runtime Reliability &amp; Centralized Rate Limits');
    expect(html).toContain('Reset All Breakers');
  });

  it('renders CostComparison initial loading state', () => {
    const html = renderToStaticMarkup(<CostComparison />);
    expect(html).toContain('Cloud Usage &amp; Cost Accounting');
    expect(html).toContain('fetching usage ledger');
  });
});
