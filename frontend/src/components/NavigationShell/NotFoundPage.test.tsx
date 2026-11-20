import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { NotFoundPage } from "./NotFoundPage";
import "../../i18n/index";

describe("NotFoundPage", () => {
  it("names the unknown path and offers a way back", () => {
    render(
      <MemoryRouter initialEntries={["/does-not-exist"]}>
        <NotFoundPage />
      </MemoryRouter>
    );

    expect(screen.getByTestId("not-found-page")).toBeInTheDocument();
    expect(screen.getByText("/does-not-exist")).toBeInTheDocument();
    expect(screen.getByTestId("not-found-home")).toHaveAttribute("href", "/");
  });
});
