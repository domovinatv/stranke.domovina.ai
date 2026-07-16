import { createBrowserRouter } from "react-router-dom";
import { lazy, Suspense } from "react";
import { RootLayout } from "./components/RootLayout";
import { PageSpinner } from "./components/PageSpinner";

const Home = lazy(() => import("./routes/Home"));
const Map = lazy(() => import("./routes/Map"));
const Party = lazy(() => import("./routes/Party"));
const City = lazy(() => import("./routes/City"));
const Stats = lazy(() => import("./routes/Stats"));
const About = lazy(() => import("./routes/About"));
const NotFound = lazy(() => import("./routes/NotFound"));

const lazyRoute = (Cmp: React.LazyExoticComponent<() => JSX.Element>) => (
  <Suspense fallback={<PageSpinner />}>
    <Cmp />
  </Suspense>
);

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    errorElement: <RootLayout error />,
    children: [
      { index: true, element: lazyRoute(Home) },
      { path: "karta", element: lazyRoute(Map) },
      { path: "stranka/:slug", element: lazyRoute(Party) },
      { path: "grad/:name", element: lazyRoute(City) },
      { path: "statistika", element: lazyRoute(Stats) },
      { path: "o-projektu", element: lazyRoute(About) },
      { path: "*", element: lazyRoute(NotFound) },
    ],
  },
]);
