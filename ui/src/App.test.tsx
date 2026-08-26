import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

// The review shell renders and, with no tenant set, prompts for one instead of calling the API.
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  // Keep background health/options requests pending so this shell test stays deterministic.
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
});

test("renders the review shell with a workspace field", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /Turn every customer message into a case/i })).toBeDefined();
  expect(screen.getByLabelText(/workspace id/i)).toBeDefined();
  // No workspace → the product explains the pilot access requirement before showing an empty app shell.
  expect(screen.getByText(/Use the workspace ID from your administrator/i)).toBeDefined();
});

test("keeps incomplete workspace IDs out of the review application", () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText(/workspace id/i), { target: { value: "not-a-workspace" } });
  fireEvent.click(screen.getByRole("button", { name: /Continue to workspace/i }));
  expect(screen.getByText(/Enter the complete workspace ID/i)).toBeDefined();
});
