import './article-body.css';

/** Reading breaks for legacy flat text. No rewriting, HTML parsing or formula guessing. */
export function readingParagraphs(text: string): string[] {
  if (text.length <= 700 || text.includes('\n')) return [text];

  const sentences = new Intl.Segmenter(undefined, {
    granularity: 'sentence',
  }).segment(text);

  const paragraphs: string[] = [];
  let current = '';
  let count = 0;

  for (const { segment } of sentences) {
    current += segment;
    count++;

    if (current.length >= 500 || count >= 3) {
      paragraphs.push(current.trim());
      current = '';
      count = 0;
    }
  }

  if (current.trim()) paragraphs.push(current.trim());
  return paragraphs;
}

export function ArticleBody({ text }: { text: string }) {
  const blocks = text
    .replace(/\r\n?/g, '\n')
    .trim()
    .split(/\n\s*\n/)
    .filter(Boolean);

  return (
    <section
      className="article-content article-body"
      aria-label="Article text"
    >
      <h2 className="tiny-label">ARTICLE TEXT</h2>

      {!blocks.length && <p>No article text available.</p>}

      {blocks.map((block, index) => {
        const heading = /^#{1,6}\s+([^\n]+)$/.exec(block.trim());

        if (heading) {
          return <h3 key={index}>{heading[1]}</h3>;
        }

        const lines = block.trim().split('\n');

        if (lines.every(line => /^\s*[-*•]\s+/.test(line))) {
          return (
            <ul key={index}>
              {lines.map((line, item) => (
                <li key={item}>
                  {line.replace(/^\s*[-*•]\s+/, '')}
                </li>
              ))}
            </ul>
          );
        }

        return readingParagraphs(block).map((paragraph, part) => (
          <p key={`${index}-${part}`}>{paragraph}</p>
        ));
      })}
    </section>
  );
}