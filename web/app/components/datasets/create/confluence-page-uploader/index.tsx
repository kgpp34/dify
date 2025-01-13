import React, { useCallback, useEffect, useState } from 'react'
import { useContext } from 'use-context-selector'
import { v4 as uuid4 } from 'uuid'
import s from './index.module.css' // 引入样式文件
import type { ConfluencePage, FileItem } from '@/models/datasets'
import { ToastContext } from '@/app/components/base/toast'
import cn from '@/utils/classnames'
import { upload } from '@/service/base' // 引入 upload 函数

type ConfluencePageUploaderProps = {
  confluencePageList: ConfluencePage[] // 当前的 Confluence 页面列表
  onConfluenceListUpdate: (pages: ConfluencePage[]) => void // Confluence 页面列表变化回调
}

const ConfluencePageUploader: React.FC<ConfluencePageUploaderProps> = ({
  confluencePageList,
  onConfluenceListUpdate,
}) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { notify } = useContext(ToastContext)
  const [urls, setUrls] = useState<string[]>([]) // 存储用户输入的URLs
  const [inputValue, setInputValue] = useState('') // 输入框的值

  useEffect(() => {
    console.log('confluencePageList updated:', confluencePageList)
  }, [confluencePageList])

  // 获取文件类型
  const getFileType = useCallback((file: File) => {
    const arr = file.name.split('.')
    return arr[arr.length - 1]
  }, [])

  // 获取文件大小
  const getFileSize = useCallback((size: number) => {
    if (size / 1024 < 10)
      return `${(size / 1024).toFixed(2)}KB`
    return `${(size / 1024 / 1024).toFixed(2)}MB`
  }, [])

  // 单个文件上传逻辑
  const fileUpload = useCallback(
    async (fileItem: FileItem, pageList: ConfluencePage[], pageIndex: number): Promise<FileItem> => {
      const formData = new FormData()
      formData.append('file', fileItem.file)

      const onProgress = (e: ProgressEvent) => {
        if (e.lengthComputable) {
          const percent = Math.floor((e.loaded / e.total) * 100)
          console.log(`File ${fileItem.file.name} progress: ${percent}%`)
          const updatedPageList = pageList.map((page, index) => {
            if (index === pageIndex) {
              return {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID ? { ...child, progress: percent } : child,
                ),
              }
            }
            return page
          })
          onConfluenceListUpdate(updatedPageList)
        }
      }

      return upload(
        {
          xhr: new XMLHttpRequest(),
          data: formData,
          onprogress: onProgress,
        },
        false,
        undefined,
        '?source=datasets',
      )
        .then((res: File) => {
          const updatedFileItem = {
            ...fileItem,
            progress: 100,
            file: res,
          }
          const updatedPageList = pageList.map((page, index) => {
            if (index === pageIndex) {
              return {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID ? updatedFileItem : child,
                ),
              }
            }
            return page
          })
          onConfluenceListUpdate(updatedPageList)
          return Promise.resolve(updatedFileItem)
        })
        .catch((err) => {
          notify({ type: 'error', message: 'File upload failed' })
          console.error(err)
          const updatedFileItem = { ...fileItem, progress: -2 }
          const updatedPageList = pageList.map((page, index) => {
            if (index === pageIndex) {
              return {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID ? updatedFileItem : child,
                ),
              }
            }
            return page
          })
          onConfluenceListUpdate(updatedPageList)
          return Promise.resolve(updatedFileItem)
        })
    },
    [notify, onConfluenceListUpdate],
  )

  // 批量上传文件
  const uploadBatchFiles = useCallback(
    async (fileItems: FileItem[], pageList: ConfluencePage[], pageIndex: number) => {
      // Create a mutable copy of the page list that we'll update throughout the process
      let updatedPageList = pageList.map((page, index) => {
        if (index === pageIndex) {
          return {
            ...page,
            children: page.children.map((child) => {
              const fileItemToUpdate = fileItems.find(file => file.fileID === child.fileID)
              if (fileItemToUpdate)
                return { ...child, progress: 0 }
              return child
            }),
          }
        }
        return page
      })

      // Initial update with 0 progress
      onConfluenceListUpdate(updatedPageList)

      // Upload files sequentially and maintain the latest state
      for (const fileItem of fileItems) {
        try {
          // Pass the latest state to fileUpload
          const updatedFileItem = await fileUpload(fileItem, updatedPageList, pageIndex)

          // Update our local copy with the latest state
          updatedPageList = updatedPageList.map((page, index) => {
            if (index === pageIndex) {
              return {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID ? updatedFileItem : child,
                ),
              }
            }
            return page
          })

          // Update the UI with the latest state
          onConfluenceListUpdate(updatedPageList)
        }
        catch (error) {
          console.error(`Failed to upload file ${fileItem.file.name}:`, error)

          // Update our local copy with the error state
          updatedPageList = updatedPageList.map((page, index) => {
            if (index === pageIndex) {
              return {
                ...page,
                children: page.children.map(child =>
                  child.fileID === fileItem.fileID ? { ...child, progress: -2 } : child,
                ),
              }
            }
            return page
          })

          // Update the UI with the error state
          onConfluenceListUpdate(updatedPageList)
        }
      }

      return updatedPageList
    },
    [fileUpload, onConfluenceListUpdate],
  )

  // 分批次上传文件
  const uploadMultipleFiles = useCallback(
    async (fileItems: FileItem[], pageList: ConfluencePage[], pageIndex: number) => {
      const BATCH_COUNT_LIMIT = 3 // 每批次上传的文件数量
      const length = fileItems.length
      let start = 0

      while (start < length) {
        const end = Math.min(start + BATCH_COUNT_LIMIT, length)
        const batchFiles = fileItems.slice(start, end)
        await uploadBatchFiles(batchFiles, pageList, pageIndex)
        start = end
      }
    },
    [uploadBatchFiles],
  )

  // 删除文件
  const removeFile = useCallback(
    (fileID: string, pageIndex: number) => {
      const updatedPageList = confluencePageList.map((page, index) =>
        index === pageIndex
          ? {
            ...page,
            children: page.children.filter(item => item.fileID !== fileID),
          }
          : page,
      )
      onConfluenceListUpdate(updatedPageList) // 触发页面列表变化回调
    },
    [confluencePageList, onConfluenceListUpdate],
  )

  // 处理 Confluence URL 输入
  const handleUrlChange = useCallback(
    async (url: string) => {
      const pageIdMatch = url.match(/pageId=(\d+)/)
      if (!pageIdMatch) {
        notify({ type: 'error', message: 'Invalid Confluence Page URL' })
        return
      }

      const pageId = pageIdMatch[1]

      setLoading(true)
      setError(null)

      try {
        const response = await fetch(`/confluence2md/page/${pageId}`)
        if (!response.ok)
          throw new Error('Failed to convert Confluence page to Markdown')

        // 获取纯文本内容
        const textContent = await response.text()

        // 根据 <!-- Page: xxxx --> 切分内容
        const sections = textContent.split(/<!--\s*Page:\s*(.*?)\s*-->/)

        // 过滤掉空内容，并提取文件名和内容
        const files: { name: string; content: string }[] = []
        for (let i = 1; i < sections.length; i += 2) {
          const name = sections[i].trim() // 提取文件名
          const content = sections[i + 1].trim() // 提取内容
          if (name && content)
            files.push({ name, content })
        }

        // 检查是否已经存在该页面
        const existingPageIndex = confluencePageList.findIndex(page => page.pageId === pageId)
        let updatedPageList: ConfluencePage[]

        if (existingPageIndex !== -1) {
          // 如果页面已存在，更新该页面的文件列表
          updatedPageList = confluencePageList.map((page, index) =>
            index === existingPageIndex
              ? {
                ...page,
                children: [
                  ...page.children,
                  ...files.map(file => ({
                    fileID: uuid4(),
                    file: new File([file.content], `${file.name}.txt`, { type: 'text/plain' }),
                    progress: 0,
                  })),
                ],
              }
              : page,
          )
        }
        else {
          // 如果页面不存在，创建一个新的 ConfluencePage
          const newPage: ConfluencePage = {
            pageId,
            space: '',
            title: '',
            children: files.map(file => ({
              fileID: uuid4(),
              file: new File([file.content], `${file.name}.txt`, { type: 'text/plain' }),
              progress: 0,
            })),
          }
          updatedPageList = [...confluencePageList, newPage]
        }

        // 更新页面列表
        onConfluenceListUpdate(updatedPageList)

        // 分批次上传文件
        await uploadMultipleFiles(
          updatedPageList[existingPageIndex !== -1 ? existingPageIndex : updatedPageList.length - 1].children,
          updatedPageList,
          existingPageIndex !== -1 ? existingPageIndex : updatedPageList.length - 1,
        )
      }
      catch (err) {
        setError('Error converting Confluence page to Markdown')
        console.error(err)
      }
      finally {
        setLoading(false)
      }
    },
    [confluencePageList, notify, onConfluenceListUpdate, uploadMultipleFiles],
  )

  // 处理输入框变化
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newUrl = e.target.value.trim()
      setInputValue(newUrl)
      if (newUrl && !urls.includes(newUrl)) {
        setUrls([...urls, newUrl])
        handleUrlChange(newUrl)
        setInputValue('')
      }
    },
    [handleUrlChange, urls],
  )

  // 处理删除URL
  const handleRemoveUrl = useCallback(
    (urlToRemove: string) => {
      setUrls(urls.filter(url => url !== urlToRemove))
    },
    [urls],
  )

  return (
    <div className={s.confluencePageUploader}>
      <div className={s.inputContainer}>
        <div className={s.inputWithTags}>
          {urls.map((url, index) => (
            <div key={index} className={s.urlTag}>
              {url}
              <span className={s.removeTag} onClick={() => handleRemoveUrl(url)}>
                ×
              </span>
            </div>
          ))}
          <input
            type="text"
            placeholder={urls.length === 0 ? 'Enter Confluence Page URL' : ''}
            className={s.input}
            value={inputValue}
            onChange={handleInputChange}
            disabled={loading}
            style={{ width: '100%' }} // 调整输入框宽度
          />
        </div>
        {loading && <div className={s.loadingSpinner} />}
      </div>
      {error && <div className={s.errorMessage}>{error}</div>}

      {/* 文件列表 */}
      <div className={s.fileList}>
        {confluencePageList.map((page, pageIndex) => (
          <div key={page.pageId} className={s.pageContainer}>
            <div className={s.fileList}>
              {page.children.map(fileItem => (
                <div key={fileItem.fileID} className={cn(s.file, fileItem.progress < 100 && s.uploading)}>
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
                    {fileItem.progress === 100 && (
                      <div
                        className={s.remove}
                        onClick={(e) => {
                          e.stopPropagation()
                          removeFile(fileItem.fileID, pageIndex) // 移除文件
                        }}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ConfluencePageUploader
