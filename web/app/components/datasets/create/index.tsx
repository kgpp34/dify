'use client'
import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import AppUnavailable from '../../base/app-unavailable'
import { ModelTypeEnum } from '../../header/account-setting/model-provider-page/declarations'
import StepOne from './step-one'
import StepTwo from './step-two'
import StepThree from './step-three'
import { TopBar } from './top-bar'
import { DataSourceType } from '@/models/datasets'
import type { CrawlOptions, CrawlResultItem, CustomFile, DataSet, FileItem, createDocumentResponse } from '@/models/datasets'
import { fetchDataSource } from '@/service/common'
import { fetchDatasetDetail, fetchUnusedFiles } from '@/service/datasets'
import { DataSourceProvider, type NotionPage } from '@/models/common'
import { useModalContext } from '@/context/modal-context'
import { useDefaultModel } from '@/app/components/header/account-setting/model-provider-page/hooks'
import { useContext } from 'use-context-selector'
import { ToastContext } from '@/app/components/base/toast'

type DatasetUpdateFormProps = {
  datasetId?: string
}

const DEFAULT_CRAWL_OPTIONS: CrawlOptions = {
  crawl_sub_pages: true,
  only_main_content: true,
  includes: '',
  excludes: '',
  limit: 10,
  max_depth: '',
  use_sitemap: true,
}

const DatasetUpdateForm = ({ datasetId }: DatasetUpdateFormProps) => {
  const { t } = useTranslation()
  const { setShowAccountSettingModal } = useModalContext()
  const { notify } = useContext(ToastContext)
  const [hasConnection, setHasConnection] = useState(true)
  const [dataSourceType, setDataSourceType] = useState<DataSourceType>(DataSourceType.FILE)
  const [step, setStep] = useState(1)
  const [indexingTypeCache, setIndexTypeCache] = useState('')
  const [retrievalMethodCache, setRetrievalMethodCache] = useState('')
  const [fileList, setFiles] = useState<FileItem[]>([])
  const [result, setResult] = useState<any>()
  const [hasError, setHasError] = useState(false)
  const { data: embeddingsDefaultModel } = useDefaultModel(ModelTypeEnum.textEmbedding)
  const [initialUnusedFilesFetched, setInitialUnusedFilesFetched] = useState(false)

  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const updateNotionPages = (value: NotionPage[]) => {
    setNotionPages(value)
  }

  const [websitePages, setWebsitePages] = useState<CrawlResultItem[]>([])
  const [crawlOptions, setCrawlOptions] = useState<CrawlOptions>(DEFAULT_CRAWL_OPTIONS)

  const updateFileList = (preparedFiles: FileItem[]) => {
    setFiles(preparedFiles)
  }
  const [websiteCrawlProvider, setWebsiteCrawlProvider] = useState<DataSourceProvider>(DataSourceProvider.fireCrawl)
  const [websiteCrawlJobId, setWebsiteCrawlJobId] = useState('')

  const updateFile = (fileItem: FileItem, progress: number, list: FileItem[]) => {
    const targetIndex = list.findIndex(file => file.fileID === fileItem.fileID)
    list[targetIndex] = {
      ...list[targetIndex],
      progress,
    }
    setFiles([...list])
    // use follow code would cause dirty list update problem
    // const newList = list.map((file) => {
    //   if (file.fileID === fileItem.fileID) {
    //     return {
    //       ...fileItem,
    //       progress,
    //     }
    //   }
    //   return file
    // })
    // setFiles(newList)
  }
  const updateIndexingTypeCache = (type: string) => {
    setIndexTypeCache(type)
  }
  const updateResultCache = (res?: createDocumentResponse) => {
    setResult(res)
  }
  const updateRetrievalMethodCache = (method: string) => {
    setRetrievalMethodCache(method)
  }

  const nextStep = useCallback(() => {
    setStep(step + 1)
  }, [step, setStep])

  const changeStep = useCallback((delta: number) => {
    setStep(step + delta)
  }, [step, setStep])

  const checkNotionConnection = async () => {
    const { data } = await fetchDataSource({ url: '/data-source/integrates' })
    const hasConnection = data.filter(item => item.provider === 'notion') || []
    setHasConnection(hasConnection.length > 0)
  }

  // 获取未使用的文件
  const fetchUnusedFilesData = useCallback(async () => {
    try {
      const unusedFiles = await fetchUnusedFiles()
      // 如果有未使用的文件，显示提示
      if (unusedFiles && unusedFiles.length > 0) {
        notify({
          type: 'info',
          message: t('datasetCreation.unusedFiles.message', { count: unusedFiles.length }),
          duration: 5000,
        })

        // 将未使用的文件转换为FileItem格式
        const unusedFileItems: FileItem[] = unusedFiles.map((file: CustomFile) => ({
          fileID: file.id,
          file: {
            ...file,
            id: file.id,
            name: file.name,
            size: file.size,
            mime_type: file.mime_type,
            extension: file.extension,
          } as CustomFile,
          progress: 100,
        }))

        // 函数式更新，确保基于最新的 fileList
        setFiles((prevFiles) => {
          const existingFileIds = prevFiles.map(item => item.fileID)
          const newFileItems = unusedFileItems.filter(item => !existingFileIds.includes(item.fileID))
          return [...prevFiles, ...newFileItems]
        })
      }
    }
    catch (error) {
      console.error('获取未使用文件失败:', error)
    }
  }, [notify, t, setFiles])

  // 当step变为1时或组件首次挂载时获取未使用文件
  useEffect(() => {
    if (step === 1 && !initialUnusedFilesFetched) {
      fetchUnusedFilesData()
      setInitialUnusedFilesFetched(true)
    }
  }, [step, initialUnusedFilesFetched, fetchUnusedFilesData])

  useEffect(() => {
    checkNotionConnection()
  }, [])

  const [detail, setDetail] = useState<DataSet | null>(null)
  useEffect(() => {
    (async () => {
      if (datasetId) {
        try {
          const detail = await fetchDatasetDetail(datasetId)
          setDetail(detail)
        }
        catch {
          setHasError(true)
        }
      }
    })()
  }, [datasetId])

  if (hasError)
    return <AppUnavailable code={500} unknownReason={t('datasetCreation.error.unavailable') as string} />

  return (
    <div className='flex flex-col bg-components-panel-bg' style={{ height: 'calc(100vh - 56px)' }}>
      <TopBar activeIndex={step - 1} datasetId={datasetId} />
      <div style={{ height: 'calc(100% - 52px)' }}>
        {step === 1 && <StepOne
          hasConnection={hasConnection}
          onSetting={() => setShowAccountSettingModal({ payload: 'data-source' })}
          datasetId={datasetId}
          dataSourceType={dataSourceType}
          dataSourceTypeDisable={!!detail?.data_source_type}
          changeType={setDataSourceType}
          files={fileList}
          updateFile={updateFile}
          updateFileList={updateFileList}
          notionPages={notionPages}
          updateNotionPages={updateNotionPages}
          onStepChange={nextStep}
          websitePages={websitePages}
          updateWebsitePages={setWebsitePages}
          onWebsiteCrawlProviderChange={setWebsiteCrawlProvider}
          onWebsiteCrawlJobIdChange={setWebsiteCrawlJobId}
          crawlOptions={crawlOptions}
          onCrawlOptionsChange={setCrawlOptions}
        />}
        {(step === 2 && (!datasetId || (datasetId && !!detail))) && <StepTwo
          isAPIKeySet={!!embeddingsDefaultModel}
          onSetting={() => setShowAccountSettingModal({ payload: 'provider' })}
          indexingType={detail?.indexing_technique}
          datasetId={datasetId}
          dataSourceType={dataSourceType}
          files={fileList.map(file => file.file)}
          notionPages={notionPages}
          websitePages={websitePages}
          websiteCrawlProvider={websiteCrawlProvider}
          websiteCrawlJobId={websiteCrawlJobId}
          onStepChange={changeStep}
          updateIndexingTypeCache={updateIndexingTypeCache}
          updateRetrievalMethodCache={updateRetrievalMethodCache}
          updateResultCache={updateResultCache}
          crawlOptions={crawlOptions}
        />}
        {step === 3 && <StepThree
          datasetId={datasetId}
          datasetName={detail?.name}
          indexingType={detail?.indexing_technique || indexingTypeCache}
          retrievalMethod={detail?.retrieval_model_dict?.search_method || retrievalMethodCache}
          creationCache={result}
        />}
      </div>
    </div>
  )
}

export default DatasetUpdateForm
