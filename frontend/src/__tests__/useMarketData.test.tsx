import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useMarketData } from "@/hooks/useMarketData";
import { MockEventSource } from "./setup";

describe("useMarketData", () => {
  it("subscribes to the SSE price stream", async () => {
    renderHook(() => useMarketData());

    await waitFor(() => expect(MockEventSource.last).not.toBeNull());
    expect(MockEventSource.last!.url).toBe("/api/stream/prices");
  });

  it("records named price events pushed by the server", async () => {
    const { result } = renderHook(() => useMarketData());
    await waitFor(() => expect(MockEventSource.last).not.toBeNull());

    act(() => {
      MockEventSource.last!.emit("price", {
        ticker: "AAPL",
        price: 191.25,
        previous_price: 190.0,
        direction: "up",
        timestamp: "2026-01-01T00:00:00Z",
      });
    });

    await waitFor(() => {
      expect(result.current.prices.AAPL?.price).toBe(191.25);
    });
    expect(result.current.prices.AAPL?.direction).toBe("up");
  });

  it("reports connected once the stream opens", async () => {
    const { result } = renderHook(() => useMarketData());

    await waitFor(() => {
      expect(MockEventSource.last?.readyState).toBe(MockEventSource.OPEN);
    });
    await waitFor(() => expect(result.current.connectionStatus).toBe("connected"));
  });

  it("reports reconnecting when the stream errors", async () => {
    const { result } = renderHook(() => useMarketData());
    await waitFor(() => expect(result.current.connectionStatus).toBe("connected"));

    act(() => {
      MockEventSource.last!.fail();
    });

    await waitFor(() => expect(result.current.connectionStatus).toBe("reconnecting"));
  });

  it("closes the stream on unmount", async () => {
    const { unmount } = renderHook(() => useMarketData());
    await waitFor(() => expect(MockEventSource.last).not.toBeNull());
    const es = MockEventSource.last!;

    unmount();

    expect(es.close).toHaveBeenCalled();
  });

  it("accumulates price history for sparklines", async () => {
    const { result } = renderHook(() => useMarketData());
    await waitFor(() => expect(MockEventSource.last).not.toBeNull());

    for (const price of [100, 101, 102]) {
      act(() => {
        MockEventSource.last!.emit("price", {
          ticker: "MSFT",
          price,
          previous_price: price - 1,
          direction: "up",
          timestamp: new Date(price).toISOString(),
        });
      });
    }

    await waitFor(() => {
      expect(result.current.priceHistory.MSFT?.length).toBe(3);
    });
    expect(result.current.priceHistory.MSFT.map((p) => p.price)).toEqual([100, 101, 102]);
  });
});
