import React, { useState } from 'react';
import { ConfluencePage, FileItem } from '@/models/datasets';
import { upload } from '@/service/base';
import { ToastContext } from '@/app/components/base/toast';
import { useContext } from 'use-context-selector';
import cn from '@/utils/classnames';
import s from './index.module.css'; // 引入样式文件

type ConfluencePageUploaderProps = {
  confluencePageList: ConfluencePage[]; // 当前的 Confluence 页面列表
  onPageListChange: (pages: ConfluencePage[]) => void; // Confluence 页面列表变化回调
};

const ConfluencePageUploader: React.FC<ConfluencePageUploaderProps> = ({
  confluencePageList,
  onPageListChange,
}) => {
  const [loading, setLoading] = useState(false);
  const { notify } = useContext(ToastContext);

  // 获取文件类型
  const getFileType = (file: File) => {
    const arr = file.name.split('.');
    return arr[arr.length - 1];
  };

  // 获取文件大小
  const getFileSize = (size: number) => {
    if (size / 1024 < 10) return `${(size / 1024).toFixed(2)}KB`;
    return `${(size / 1024 / 1024).toFixed(2)}MB`;
  };

  // 处理 Confluence URL 输入
  const handleUrlChange = async (url: string) => {
    const pageIdMatch = url.match(/pageId=(\d+)/);
    if (!pageIdMatch) {
      notify({ type: 'error', message: 'Invalid Confluence Page URL' });
      return;
    }

    const pageId = pageIdMatch[1];

    setLoading(true);

    try {
      const response = await fetch(`/confluence2md/page/${pageId}`);
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
        progress: 0, // 初始进度为0
      };

      // 检查是否已经存在该页面
      const existingPageIndex = confluencePageList.findIndex((page) => page.pageId === pageId);
      let updatedPageList: ConfluencePage[];

      if (existingPageIndex !== -1) {
        // 如果页面已存在，更新该页面的文件列表
        updatedPageList = confluencePageList.map((page, index) =>
          index === existingPageIndex
            ? { ...page, children: [...page.children, fileItem] }
            : page
        );
      } else {
        // 如果页面不存在，创建一个新的 ConfluencePage
        const newPage: ConfluencePage = {
          pageId: pageId,
          space: '',
          title: '',
          children: [fileItem],
        };
        updatedPageList = [...confluencePageList, newPage];
      }

      onPageListChange(updatedPageList); // 触发页面列表变化回调

      // 开始上传文件
      await fileUpload(fileItem, updatedPageList, existingPageIndex !== -1 ? existingPageIndex : updatedPageList.length - 1);
    } catch (err) {
      notify({ type: 'error', message: 'Error converting Confluence page to Markdown' });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // 文件上传逻辑
  const fileUpload = async (
    fileItem: FileItem,
    pageList: ConfluencePage[],
    pageIndex: number
  ): Promise<void> => {
    const formData = new FormData();
    formData.append('file', fileItem.file);

    const onProgress = (e: ProgressEvent) => {
      if (e.lengthComputable) {
        const percent = Math.floor((e.loaded / e.total) * 100);
        // 更新文件上传进度
        const updatedFileItem = { ...fileItem, progress: percent };
        const updatedPageList = pageList.map((page, index) =>
          index === pageIndex
            ? {
                ...page,
                children: page.children.map((item) =>
                  item.fileID === fileItem.fileID ? updatedFileItem : item
                ),
              }
            : page
        );
        onPageListChange(updatedPageList); // 触发页面列表变化回调
      }
    };

    try {
      const response = await upload({
        xhr: new XMLHttpRequest(),
        data: formData,
        onprogress: onProgress,
      }, false, undefined, '?source=datasets');

      if (response) {
        // 上传成功，更新文件项
        const updatedFileItem = {
          ...fileItem,
          progress: 100,
          file: response, // 更新文件对象
        };
        const updatedPageList = pageList.map((page, index) =>
          index === pageIndex
            ? {
                ...page,
                children: page.children.map((item) =>
                  item.fileID === fileItem.fileID ? updatedFileItem : item
                ),
              }
            : page
        );
        onPageListChange(updatedPageList); // 触发页面列表变化回调
      }
    } catch (err) {
      notify({ type: 'error', message: 'File upload failed' });
      console.error(err);

      // 上传失败，更新文件状态
      const updatedFileItem = { ...fileItem, progress: -2 };
      const updatedPageList = pageList.map((page, index) =>
        index === pageIndex
          ? {
              ...page,
              children: page.children.map((item) =>
                item.fileID === fileItem.fileID ? updatedFileItem : item
              ),
            }
          : page
      );
      onPageListChange(updatedPageList); // 触发页面列表变化回调
    }
  };

  return (
    <div className={s.confluencePageUploader}>
      <input
        type="text"
        placeholder="Enter Confluence Page URL"
        className={s.input}
        onChange={(e) => handleUrlChange(e.target.value)}
        disabled={loading}
      />
      {loading && <p className={s.loading}>Loading...</p>}

      {confluencePageList.map((page, pageIndex) => (
        <div key={page.pageId} className={s.pageContainer}>
          <h3 className={s.pageTitle}>{page.title || `Page ${page.pageId}`}</h3>
          <div className={s.fileList}>
            {page.children.map((fileItem, fileIndex) => (
              <div
                key={`${fileItem.fileID}-${fileIndex}`}
                className={cn(
                  s.file,
                  fileItem.progress < 100 && s.uploading,
                )}
              >
                {fileItem.progress < 100 && (
                  <div className={s.progressbar} style={{ width: `${fileItem.progress}%` }} />
                )}
                <div className={s.fileInfo}>
                  <div className={cn(s.fileIcon, s[getFileType(fileItem.file)])} />
                  <div className={s.filename}>{fileItem.file.name}</div>
                  <div className={s.size}>{getFileSize(fileItem.file.size)}</div>
                </div>
                <div className={s.actionWrapper}>
                  {fileItem.progress < 100 && fileItem.progress >= 0 && (
                    <div className={s.percent}>{`${fileItem.progress}%`}</div>
                  )}
                  {fileItem.progress === -2 && (
                    <div className={s.error}>Upload Failed</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ConfluencePageUploader;