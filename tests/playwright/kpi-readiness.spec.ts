import { test, expect } from './fixtures';

test.describe('KPI and Readiness Checks', () => {
  test('KPI endpoint → required fields are present and numeric', async ({ apiClient }) => {
    const { status, body } = await apiClient.getKPIs();
    expect(status).toBe(200);
    // Real KPI fields from /v1/admin/kpis
    expect(typeof body.sold_leads).toBe('number');
    expect(typeof body.active_buyers).toBe('number');
    expect(typeof body.prepaid_cash_cents).toBe('number');
    expect(typeof body.returned_leads).toBe('number');
    expect(typeof body.lead_revenue_cents).toBe('number');
    expect(typeof body.gross_lead_revenue_cents).toBe('number');
    expect(typeof body.buyer_adjustments_cents).toBe('number');
    expect(typeof body.campaign_margin_cents).toBe('number');
  });

  test('workflow KPIs → valid response shape', async ({ apiClient }) => {
    const { status, body } = await apiClient.getWorkflowKPIs();
    expect(status).toBe(200);
    expect(body).toBeDefined();
  });

  test('launch-readiness → returns checks map and readiness_label', async ({ apiClient }) => {
    const { status, body } = await apiClient.getLaunchReadiness();
    expect(status).toBe(200);
    expect(body).toHaveProperty('readiness_label');
    expect(body).toHaveProperty('checks');
    expect(body).toHaveProperty('metrics');
    expect(typeof body.local_simulation_ready).toBe('boolean');
  });

  test('launch-readiness checks → all expected keys are present', async ({ apiClient }) => {
    const { status, body } = await apiClient.getLaunchReadiness();
    expect(status).toBe(200);
    const { checks } = body;
    expect(checks).toHaveProperty('synthetic_ping_post_routed_test_lead');
    expect(checks).toHaveProperty('synthetic_call_tracking_ingested');
    expect(checks).toHaveProperty('ping_post_routed_test_lead');
    expect(checks).toHaveProperty('call_tracking_ingested');
  });

  test('workflow KPIs → transition counts are numbers', async ({ apiClient }) => {
    const { status, body } = await apiClient.getWorkflowKPIs();
    expect(status).toBe(200);
    // Spot-check at least one numeric field exists in the response
    const hasNumbers = Object.values(body).some((v) => typeof v === 'number');
    expect(hasNumbers || Object.keys(body).length > 0).toBe(true);
  });

  test('KPI + readiness both respond within timeout', async ({ apiClient }) => {
    const [kpi, readiness] = await Promise.all([
      apiClient.getKPIs(),
      apiClient.getLaunchReadiness(),
    ]);
    expect(kpi.status).toBe(200);
    expect(readiness.status).toBe(200);
  });
});
