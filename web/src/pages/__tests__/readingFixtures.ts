import type { DigestView } from '../../api/generated';

export function savedDigest(
  day = '2026-10-30',
  content = '**Evidence first.**\n\n- A useful finding',
): DigestView {
  return {
    digest_id: `digest-${day}`,
    digest_date: day,
    generated_at: `${day}T18:00:00Z`,
    total_items: 1,

    sections: [
      {
        section_id: 'news',
        section_title: 'News & ideas',
        category: 'news',
        items: [
          {
            knowledge_id: 'story-one',
            title: 'An interesting discovery',
            summary: 'A concise summary.',
            source_name: 'Research lab',
            source_url: 'https://example.org/research',
            published_at: `${day}T09:00:00Z`,
            relevance_score: .8,
            importance_score: .9,
            topics: ['AI'],
            source_type: 'rss',
            date_basis: 'published_at',
            fetched_at: `${day}T10:00:00Z`,
            score_computed_at: `${day}T11:00:00Z`,
          },
        ],
      },
    ],

    topic_groups: { AI: ['story-one'] },

    intelligence: {
      document_id: `report-${day}`,
      date: day,
      generated_at: `${day}T17:00:00Z`,
      metadata: {
        total_insights: 0,
        total_trends: 0,
        total_citations: 0,
        confidence_avg: 0,
      },
      sections: (
        [
          'executive_summary',
          'top_trends',
          'key_insights',
          'notable_items',
        ] as const
      ).map((type, index) => ({
        section_id: type,
        section_type: type,
        title: [
          'Executive summary',
          'Top trends',
          'Key insights',
          'Notable items',
        ][index],
        content: index ? 'No further observations.' : content,
      })),
    },
  };
}