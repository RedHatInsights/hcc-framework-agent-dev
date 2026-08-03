import { test, expect } from '@playwright/test';

/**
 * GOOD EXAMPLE - No anti-patterns
 * - Uses proper waits (waitForSelector, toBeVisible)
 * - Has assertions
 * - No hard-coded sleeps
 * - Tests are enabled
 */

test.describe('Login Flow', () => {
  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('/login');

    // Wait for form to be ready
    await page.waitForSelector('#login-form');

    // Fill in credentials
    await page.fill('#username', 'testuser');
    await page.fill('#password', 'password123');

    // Submit and wait for navigation
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');

    // Verify successful login
    await expect(page.locator('.welcome-message')).toBeVisible();
    await expect(page.locator('.welcome-message')).toContainText('Welcome, testuser');
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('#username', 'invalid');
    await page.fill('#password', 'wrong');
    await page.click('button[type="submit"]');

    // Wait for error message to appear
    const errorMessage = page.locator('.error-message');
    await expect(errorMessage).toBeVisible({ timeout: 5000 });
    await expect(errorMessage).toContainText('Invalid credentials');

    // Verify we're still on login page
    await expect(page).toHaveURL(/.*login/);
  });

  test('should handle async data loading', async ({ page }) => {
    await page.goto('/dashboard');

    // Wait for API response and UI update
    await page.waitForResponse(resp =>
      resp.url().includes('/api/user') && resp.status() === 200
    );

    // Use retry-based assertion for flaky elements
    await expect(async () => {
      const items = await page.locator('.data-item').count();
      expect(items).toBeGreaterThan(0);
    }).toPass({ timeout: 10000 });
  });
});
