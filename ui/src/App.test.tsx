import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

// The review shell renders while the background session check is pending.
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  // Keep background health/options requests pending so this shell test stays deterministic.
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
});

test("renders the review shell with secure account creation", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /Turn every customer message into a case/i })).toBeDefined();
  expect(screen.getByLabelText(/work email/i)).toBeDefined();
  expect(screen.getByLabelText(/workspace name/i)).toBeDefined();
  expect(screen.getByText(/No administrator setup or workspace code needed/i)).toBeDefined();
});

test("switches between account creation and sign in", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));
  expect(screen.queryByLabelText(/workspace name/i)).toBeNull();
  expect(screen.getByRole("heading", { name: /Welcome back/i })).toBeDefined();
});
