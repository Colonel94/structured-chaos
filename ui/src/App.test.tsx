import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

// The review shell renders and, with no tenant set, prompts for one instead of calling the API.
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

test("renders the review shell with a tenant field", () => {
  render(<App />);
  expect(screen.getByText(/Adaptive Intake — Review/i)).toBeDefined();
  expect(screen.getByLabelText(/tenant id/i)).toBeDefined();
  // No tenant → no fetch, and the register prompts to set one.
  expect(screen.getByText(/Set a tenant id to load cases/i)).toBeDefined();
});
