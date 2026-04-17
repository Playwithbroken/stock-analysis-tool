import { useCallback, useEffect, useState } from "react";
import { fetchJsonWithRetry } from "../lib/api";

type PushState = "unsupported" | "default" | "denied" | "granted" | "subscribed";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

export default function usePushNotifications() {
  const [state, setState] = useState<PushState>("default");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    const perm = Notification.permission;
    if (perm === "denied") {
      setState("denied");
      return;
    }
    // Check if already subscribed
    navigator.serviceWorker.ready.then((reg) => {
      reg.pushManager.getSubscription().then((sub) => {
        setState(sub ? "subscribed" : perm === "granted" ? "granted" : "default");
      });
    });
  }, []);

  const subscribe = useCallback(async () => {
    if (state === "unsupported" || state === "denied") return false;
    setLoading(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState("denied");
        setLoading(false);
        return false;
      }

      // Get VAPID public key from server
      const { publicKey } = await fetchJsonWithRetry<{ publicKey: string }>(
        "/api/push/vapid-key",
        undefined,
        { retries: 1, retryDelayMs: 500 },
      );

      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
      });

      // Send subscription to server
      await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subscription.toJSON()),
      });

      setState("subscribed");
      setLoading(false);
      return true;
    } catch (err) {
      console.error("[Push] Subscribe failed:", err);
      setLoading(false);
      return false;
    }
  }, [state]);

  const unsubscribe = useCallback(async () => {
    try {
      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.getSubscription();
      if (subscription) {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe();
        await fetch("/api/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint }),
        });
      }
      setState("default");
    } catch (err) {
      console.error("[Push] Unsubscribe failed:", err);
    }
  }, []);

  const sendTest = useCallback(async () => {
    try {
      await fetch("/api/push/test", { method: "POST" });
    } catch {
      // ignore
    }
  }, []);

  return { state, loading, subscribe, unsubscribe, sendTest };
}
