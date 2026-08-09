import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "./App";

// Phase-0 CI proof-of-life for the UI lane; replaced by real review-screen tests in Phase 7.
test("renders the scaffold shell", () => {
  render(<App />);
  expect(screen.getByText(/review UI/i)).toBeDefined();
});
