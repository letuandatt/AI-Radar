import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAddKnowledge, addErrorText } from '../../hooks/useAddKnowledge';
import { safeUrl, storyUrl } from '../shared/Reading';
import './manual-add.css';

export function AddKnowledgeModal({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const urlInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [validation, setValidation] = useState('');
  const mutation = useAddKnowledge();

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const node = dialog.current;
    node?.showModal();
    urlInput.current?.focus();
    return () => { node?.close(); opener?.focus(); };
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (mutation.isPending) return;
    if (!safeUrl(url.trim()) || url.trim().length > 2048) {
      setValidation('Enter a complete HTTP(S) URL without embedded credentials.');
      return;
    }
    setValidation('');
    mutation.mutate({ url: url.trim(), ...(title.trim() ? { title: title.trim() } : {}) });
  }

  const result = mutation.data;
  return <dialog ref={dialog} className="manual-dialog" aria-labelledby="add-story-title"
    aria-describedby="add-story-description" onCancel={event => {
      event.preventDefault();
      if (!mutation.isPending) onClose();
    }}>
    <div className="manual-heading">
      <span className="eyebrow">SAVE SOMETHING WORTH READING</span>
      <button className="icon-button" type="button" aria-label="Close add story"
        disabled={mutation.isPending} onClick={onClose}>×</button>
    </div>
    <h2 id="add-story-title">Add to your radar.</h2>
    <p id="add-story-description" className="muted">
      Save a public article and let your configured AI providers analyze it.
      This uses your normal provider budget. HTML and text pages are supported.
    </p>
    {result ? <div className="manual-result" role="status">
      <h3>{result.status === 'existing' ? 'Already in your collection.' : 'Saved to your collection.'}</h3>
      {result.status === 'existing' && <p>The existing article and its processing state were left unchanged.</p>}
      {result.content_truncated && <p>The page was shortened to the first 10,000 text characters.</p>}
      {result.indexing === 'partial' && <p>Search indexes are incomplete. The saved article is available; rebuild the indexes with your existing maintenance flow.</p>}
      {result.analysis === 'failed' && <p>Content analysis did not finish. Run the existing analysis flow for this article.</p>}
      {result.importance === 'failed' && <p>Importance scoring did not finish. Run the existing scoring flow for this article.</p>}
      {result.importance === 'skipped' && <p>Importance scoring is waiting for content analysis.</p>}
      <Link className="pill-button primary-button" to={storyUrl(result.knowledge_id)} onClick={onClose}>
        Read saved story ↗
      </Link>
    </div> : <form onSubmit={submit}>
      <fieldset disabled={mutation.isPending}>
        <label htmlFor="manual-url">Article URL</label>
        <input id="manual-url" type="url" required maxLength={2048} ref={urlInput}
          value={url} onChange={event => setUrl(event.target.value)} placeholder="https://example.com/article" />
        <label htmlFor="manual-title">Title <span className="muted">(optional)</span></label>
        <input id="manual-title" maxLength={300} value={title} onChange={event => setTitle(event.target.value)}
          placeholder="Use the page title" />
      </fieldset>
      {validation && <p role="alert" className="manual-notice">{validation}</p>}
      {mutation.isError && <p role="alert" className="manual-notice">{addErrorText(mutation.error)}</p>}
      {mutation.isPending && <p role="status" className="manual-notice">
        Fetching, extracting and saving your story, then analyzing it. Local models may take a while.
        Keep this window open; progress is logged in the API terminal.
      </p>}
      <div className="manual-actions">
        <button type="button" className="pill-button" disabled={mutation.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="pill-button primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? 'Adding story…' : 'Save and analyze'}
        </button>
      </div>
    </form>}
  </dialog>;
}