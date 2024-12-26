import React, { useState } from 'react';
import { FileItem } from '@/models/datasets';

type ConfluencePageUploaderProps = {
  onFileUpload: (fileItem: FileItem) => void;
};

const ConfluencePageUploader: React.FC<ConfluencePageUploaderProps> = ({ onFileUpload }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUrlChange = async (url: string) => {
    const pageIdMatch = url.match(/pageId=(\d+)/);
    if (!pageIdMatch) {
      setError('Invalid Confluence Page URL');
      return;
    }

    const pageId = pageIdMatch[1];
    const conversionServer = process.env.CONFLUENCE_TO_MARKDOWN_SERVER;

    if (!conversionServer) {
      setError('Confluence to Markdown conversion server URL is not set.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${conversionServer}/confluence2md/page/${pageId}`);
      if (!response.ok) {
        throw new Error('Failed to convert Confluence page to Markdown');
      }

      // 获取纯文本内容
      const textContent = await response.text();

      // 将纯文本内容封装为 .txt 文件
      const blob = new Blob([textContent], { type: 'text/plain' });
      const file = new File([blob], `confluence-page-${pageId}.txt`, { type: 'text/plain' });

      const fileItem: FileItem = {
        fileID: `confluence-page-${pageId}`,
        file: file,
        progress: 100,
      };

      onFileUpload(fileItem);
    } catch (err) {
      setError('Error converting Confluence page to Markdown');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="text"
        placeholder="Enter Confluence Page URL"
        className="w-full p-2 border border-gray-300 rounded-md"
        onChange={(e) => handleUrlChange(e.target.value)}
        disabled={loading}
      />
      {loading && <p>Loading...</p>}
      {error && <p className="text-red-500">{error}</p>}
    </div>
  );
};

export default ConfluencePageUploader;