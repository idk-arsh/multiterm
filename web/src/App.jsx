import { IconShells } from "./icons.jsx";
import Landing, { GITHUB, RELEASES } from "./pages/Landing.jsx";

function Nav() {
  return (
    <nav className="nav">
      <div className="wrap nav-inner">
        <a className="brand" href="/">
          <span className="brand-mark">
            <IconShells width="19" height="19" />
          </span> MultiTerm
        </a>
        <div className="nav-links">
          <a className="hide-sm" href={GITHUB}>GitHub</a>
          <a className="hide-sm" href={GITHUB + "/issues"}>Issues</a>
          <a className="btn btn-primary" href={RELEASES}>Download</a>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Landing />
      </main>
      <footer>
        <div className="wrap foot-inner">
          <span>MultiTerm is MIT licensed.</span>
          <span>
            <a href={GITHUB}>Source</a> · <a href={GITHUB + "/issues"}>Report a problem</a>
          </span>
        </div>
      </footer>
    </>
  );
}
