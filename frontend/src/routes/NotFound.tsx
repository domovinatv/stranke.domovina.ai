import { Landmark } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageSpinner } from "@/components/PageSpinner";

const RELOAD_KEY = "notfound-reloaded";

/**
 * Stari service worker poslužuje stari bundle, a on ne zna za rute dodane u
 * novom deployu. Prije 404 zato provjeri ima li nove verzije: ako se instalira,
 * main.tsx osvježi stranicu na controllerchange; ovdje je samo pričuva da se
 * stranica osvježi točno jednom po adresi.
 */
function useCheckingForUpdate(): boolean {
  const [checking, setChecking] = useState(
    () =>
      "serviceWorker" in navigator &&
      !!navigator.serviceWorker.controller &&
      sessionStorage.getItem(RELOAD_KEY) !== location.pathname,
  );

  useEffect(() => {
    if (!checking) return;
    let done = false;
    const reload = () => {
      sessionStorage.setItem(RELOAD_KEY, location.pathname);
      location.reload();
    };
    const timer = setTimeout(() => !done && reload(), 8000);
    navigator.serviceWorker
      .getRegistration()
      .then(async (reg) => {
        if (!reg) throw new Error("nema registracije");
        await reg.update();
        const fresh = reg.installing ?? reg.waiting;
        if (!fresh) throw new Error("nema nove verzije");
        fresh.addEventListener("statechange", () => {
          if (fresh.state === "activated") reload();
        });
      })
      .catch(() => {
        done = true;
        clearTimeout(timer);
        setChecking(false);
      });
    return () => clearTimeout(timer);
  }, [checking]);

  return checking;
}

export default function NotFound() {
  if (useCheckingForUpdate()) return <PageSpinner />;
  return (
    <div className="container-page py-24 text-center">
      <div className="mb-4 grid place-items-center text-muted/50"><Landmark size={56} strokeWidth={1.5} /></div>
      <h1 className="text-3xl font-extrabold text-navy">404 — stranica ne postoji</h1>
      <p className="text-muted mt-2">Ovaj mandat je istekao.</p>
      <Link to="/" className="btn-primary mt-6 inline-flex">
        ← Natrag na početnu
      </Link>
    </div>
  );
}
