export interface EpubChapterMeta {
  index: number;
  title: string;
}

export interface EpubChapter extends EpubChapterMeta {
  paragraphs: string[];
}

export interface EpubBookMeta {
  filename: string;
  title: string;
  chapters: EpubChapterMeta[];
}
